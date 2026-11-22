# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""StanzaWeaver application entry point (Flask + SocketIO + pywebview).

- HTTP API: template list, LLM config, history, custom templates, import
  status;
- SocketIO: generate / feedback events drive the four-step pipeline and
  push progress/done/error;
- Security: local access only (Host check) + CSRF token protection for
  write endpoints;
- Vocabulary import on first run (background thread).
"""

import importlib.util
import inspect
import json
import os
import secrets
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

from src.logging_setup import get_logger, setup_logging
from src.templates import (
    custom_template_schemes,
    list_dicts,
    set_order,
    template_helpers,
    unregister,
)
from src.templates.en import register_english_templates
from src.templates.fr import register_french_templates
from src.templates.it import register_italian_templates
from src.templates.la import register_latin_templates
from src.templates.zh import register_chinese_templates

logger = get_logger(__name__)

setup_logging()

register_chinese_templates()
register_english_templates()
register_italian_templates()
register_french_templates()
register_latin_templates()

#: Default display order of built-in templates (registration order; used by
#: the "reset template order" action).
_DEFAULT_BUILTIN_ORDER: list[str] = [item["key"] for item in list_dicts()]

_vocab_importing = True


def _auto_import() -> None:
    """Background thread: import the vocabulary automatically on first run."""
    global _vocab_importing
    from src.knowledge.vocabulary import init_db

    try:
        init_db()
        logger.info("[StanzaWeaver] Checking vocabulary...")
        from src.knowledge.importer import import_all

        import_all()
    except Exception as e:  # noqa: BLE001 - vocabulary import failure: log only
        logger.error("[StanzaWeaver] Vocabulary import failed: %s", e)
    finally:
        _vocab_importing = False
        _llm_ping_event.set()


def _ping_one_endpoint(endpoint_name: str) -> None:
    """Probe the connectivity of a single LLM endpoint.

    Args:
        endpoint_name: Endpoint name ("writer" / "checker" / "editor").

    """
    from src.agents.base import LLMClient
    from src.config import get_config

    cfg = get_config()
    ep = getattr(cfg, endpoint_name)
    if not ep.get("api_key"):
        _llm_status[endpoint_name] = "unknown"
        return
    try:
        client = LLMClient(
            base_url=str(ep["base_url"]),
            api_key=str(ep["api_key"]),
            model=str(ep["model"]),
        )
        client.chat([{"role": "user", "content": "hi"}])
        _llm_status[endpoint_name] = "ok"
    except Exception:  # noqa: BLE001 - ping fallback
        _llm_status[endpoint_name] = "error"


def _auto_ping() -> None:
    """Probe LLM endpoints at startup, then only after config changes.

    No periodic polling: this avoids mistaking actions such as the user's
    "cancel settings" for a connectivity re-check; connectivity is refreshed
    only when config is saved (or vocabulary import finishes, or the check
    button is clicked).
    """
    time.sleep(5)
    while True:
        socketio.emit(
            "llm_status",
            {"writer": "checking", "checker": "checking", "editor": "checking"},
        )
        _ping_one_endpoint("writer")
        _ping_one_endpoint("checker")
        _ping_one_endpoint("editor")
        socketio.emit("llm_status", dict(_llm_status))
        _llm_ping_event.wait()
        _llm_ping_event.clear()


def _start_background_threads() -> None:
    """Start the background import/connectivity-probe threads on demand.

    Only called when ``start_server`` starts the HTTP service; it is skipped
    in the test environment (conftest injects STANZA_WEAVER_TEST=1) to keep
    async threads from reading a test-redirected database path and polluting
    the temporary vocabulary, and to avoid network requests on a bare
    ``import app``.
    """
    if os.environ.get("STANZA_WEAVER_TEST") != "1":
        threading.Thread(target=_auto_import, daemon=True).start()
        threading.Thread(target=_auto_ping, daemon=True).start()


app = Flask(__name__, template_folder="templates", static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_active_states: dict[str, dict[str, Any]] = {}
_active_sequences: dict[str, dict[str, Any]] = {}
_CSRF_TOKEN = secrets.token_hex(16)
_llm_status: dict[str, str] = {
    "writer": "unknown",
    "checker": "unknown",
    "editor": "unknown",
}
_llm_ping_event = threading.Event()


#: Environment variable: overrides the custom template directory (Docker or
#: portable deployments can point it at a persistent directory).
_CUSTOM_TEMPLATES_DIR_ENV = "STANZAWEAVER_TEMPLATES_DIR"


def _custom_templates_dir() -> Path:
    """Return the directory that holds custom template files.

    Source runs use the in-repo ``src/templates`` (convenient for
    development); PyInstaller builds live in an install directory that is
    usually read-only and gets replaced wholesale on upgrade, so the user
    data directory ``~/.stanza_weaver/templates`` is used instead. Can be
    overridden with ``STANZAWEAVER_TEMPLATES_DIR``.

    Returns:
        Custom template directory path (not guaranteed to exist).

    """
    override = os.environ.get(_CUSTOM_TEMPLATES_DIR_ENV, "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path.home() / ".stanza_weaver" / "templates"
    return Path(__file__).parent / "src" / "templates"


def _legacy_custom_templates_dir() -> Path | None:
    """Return the old custom template directory of compiled builds.

    It lives inside the install directory and is kept for compatibility /
    migration.

    Returns:
        Legacy directory path; None in source mode or when identical to the
        new directory.

    """
    if not getattr(sys, "frozen", False):
        return None
    legacy = Path(__file__).parent / "src" / "templates"
    try:
        if legacy.resolve() == _custom_templates_dir().resolve():
            return None
    except OSError:
        pass
    return legacy


def _migrate_legacy_custom_templates(primary: Path, legacy: Path | None) -> None:
    """Copy custom templates from the old install directory (skip existing).

    Args:
        primary: New custom template directory.
        legacy: Legacy template directory (may be None).

    """
    if legacy is None or not legacy.exists():
        return
    try:
        primary.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(
            "[StanzaWeaver] Failed to create custom template directory %s: %s",
            primary,
            e,
        )
        return
    for f in sorted(legacy.glob("custom_*.py")):
        dest = primary / f.name
        if dest.exists():
            continue
        try:
            shutil.copy2(f, dest)
            logger.info(
                "[StanzaWeaver] Migrated custom template %s -> %s", f.name, primary
            )
        except OSError as e:
            logger.warning(
                "[StanzaWeaver] Failed to migrate custom template %s: %s", f.name, e
            )


def _load_custom_template_module(file_path: Path) -> Any:
    """Load a custom template module from a file.

    Supports the user data directory of compiled builds. Generated
    templates reuse the base classes and language modules of the
    ``src.templates`` package via relative imports, so the module name is
    fixed to ``src.templates.<file name>`` regardless of the directory.

    Args:
        file_path: Template source file path.

    Returns:
        The executed module object.

    Raises:
        ImportError: When no valid module spec can be built for the file.

    """
    module_name = f"src.templates.{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load template module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def _register_custom_templates() -> None:
    """Register custom templates (restored automatically on restart).

    Source mode reads ``src/templates``; compiled builds read the user data
    directory and also migrate templates from the old install directory
    (``_internal/src/templates``). The old directory loads first and the new
    one second, so a user-directory template wins on name collisions.
    """
    primary = _custom_templates_dir()
    legacy = _legacy_custom_templates_dir()
    _migrate_legacy_custom_templates(primary, legacy)
    directories: list[Path] = []
    if legacy is not None and legacy.exists():
        directories.append(legacy)
    if primary.exists():
        directories.append(primary)
    for tpl_dir in directories:
        for f in sorted(tpl_dir.glob("custom_*.py")):
            try:
                module = _load_custom_template_module(f)
                for attr in dir(module):
                    if attr.startswith("register_custom_"):
                        getattr(module, attr)()
            except Exception as e:  # noqa: BLE001 - user code; log failures
                logger.error(
                    "[StanzaWeaver] Failed to register custom template %s: %s",
                    f.name,
                    e,
                )


def _template_order_path() -> Path:
    """Path of the file that persists the user-defined template order.

    Returns:
        ``~/.stanza_weaver/template_order.json``.

    """
    return Path.home() / ".stanza_weaver" / "template_order.json"


def _load_template_order() -> list[str]:
    """Read the saved template order.

    Returns:
        List of keys; empty when the file is missing, corrupt, or invalid.

    """
    path = _template_order_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [str(key) for key in data]


def _save_template_order(keys: list[str]) -> None:
    """Write the template order to the user data directory.

    Args:
        keys: Template keys in display order.

    Raises:
        OSError: Raised on write failure; the caller decides whether to
            report it.

    """
    path = _template_order_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(list(keys), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _default_template_order() -> list[str]:
    """Compute the template order after "reset to default".

    Built-in templates come first in their default registration order;
    custom templates keep their current relative order and are appended
    after the built-ins; the remaining templates keep their current order
    and are appended last.

    Returns:
        Full key order following the default rules.
    """
    current = [item["key"] for item in list_dicts()]
    current_set = set(current)
    builtins = [key for key in _DEFAULT_BUILTIN_ORDER if key in current_set]
    builtin_set = set(builtins)
    customs = [
        key for key in current if key.startswith("custom_") and key not in builtin_set
    ]
    extras = [
        key
        for key in current
        if key not in builtin_set and not key.startswith("custom_")
    ]
    return builtins + customs + extras


def _apply_saved_template_order() -> None:
    """Apply the saved template order at startup (skipped in tests)."""
    if os.environ.get("STANZA_WEAVER_TEST") == "1":
        return
    keys = _load_template_order()
    if keys:
        set_order(keys)


_register_custom_templates()
_apply_saved_template_order()


@app.before_request
def _guard_local_access() -> Any:
    """Allow local access only (Host check).

    Returns:
        None to pass; a jsonify Response to reject with 403.

    """
    host = request.host or ""
    if not host.startswith(("127.0.0.1", "localhost")):
        return jsonify({"status": "error", "message": "Non-local access denied"}), 403
    return None


def _require_csrf() -> bool:
    """Validate the CSRF token.

    Returns:
        True when the token matches.

    """
    return request.headers.get("X-CSRF-Token", "") == _CSRF_TOKEN


@app.route("/api/import-status")
def api_import_status() -> Any:
    """Query the vocabulary import status.

    Returns:
        JSON Response with an importing boolean field.

    """
    return jsonify({"importing": _vocab_importing})


@app.route("/api/llm-status")
def api_llm_status() -> Any:
    """Query LLM endpoint connectivity status.

    Returns:
        JSON Response with the writer and checker statuses
        ("unknown" / "checking" / "ok" / "error").

    """
    return jsonify(dict(_llm_status))


@app.route("/api/llm-ping", methods=["POST"])
def api_llm_ping() -> Any:
    """Manually trigger an LLM endpoint connectivity probe.

    Returns:
        JSON Response with the latest writer and checker statuses.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    _llm_status["writer"] = "checking"
    _llm_status["checker"] = "checking"
    _llm_status["editor"] = "checking"
    _ping_one_endpoint("writer")
    _ping_one_endpoint("checker")
    _ping_one_endpoint("editor")
    socketio.emit("llm_status", dict(_llm_status))
    return jsonify(dict(_llm_status))


_I18N_DIR = Path(__file__).parent / "i18n"


@app.route("/api/i18n/<lang>")
def api_i18n(lang: str) -> Any:
    """Return the translation JSON for the given language.

    Args:
        lang: Language code ("zh" or "en").

    Returns:
        JSON Response, translation dictionary.

    """
    if lang not in ("zh", "en"):
        lang = "zh"
    yaml_path = _I18N_DIR / f"{lang}.yaml"
    if not yaml_path.exists():
        yaml_path = _I18N_DIR / "zh.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return jsonify(data)


@app.route("/")
def index() -> str:
    """Main page (injects the CSRF token).

    Returns:
        Rendered HTML string.

    """
    return render_template("index.html", csrf_token=_CSRF_TOKEN)


@app.route("/api/templates")
def api_templates() -> Any:
    """Template list endpoint.

    Returns:
        JSON Response, list of template dictionaries.

    """
    return jsonify(list_dicts())


@app.route("/api/templates/meta")
def api_templates_meta() -> Any:
    """Per-language constraint metadata for the custom template editor.

    Returns:
        JSON Response: {language: {"attribute", "values", "helpers"}}.

    """
    meta: dict[str, dict[str, Any]] = {}
    for lang, (attribute, values) in custom_template_schemes().items():
        meta[lang] = {
            "attribute": attribute,
            "values": list(values),
            "helpers": list(template_helpers(lang)),
        }
    return jsonify(meta)


@app.route("/api/templates/order", methods=["POST"])
def api_reorder_templates() -> Any:
    """Persist the user-defined template display order.

    Returns:
        JSON Response: the reordered key list on success.

    Raises:
        400: Invalid request format.
        403: CSRF token validation failed.
        500: Failed to write the order file.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400
    raw_order = data.get("order")
    if not isinstance(raw_order, list) or not all(
        isinstance(key, str) for key in raw_order
    ):
        return jsonify(
            {"status": "error", "message": "Order must be a list of template keys"}
        ), 400
    ordered = set_order(raw_order)
    try:
        _save_template_order(ordered)
    except OSError as e:
        return jsonify(
            {"status": "error", "message": f"Failed to save template order: {e}"}
        ), 500
    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("Template order updated: %d templates", len(ordered))
    return jsonify({"status": "ok", "order": ordered})


@app.route("/api/templates/order/reset", methods=["POST"])
def api_reset_template_order() -> Any:
    """Reset the template order to the default order.

    Built-in templates return to their default order; custom templates keep
    their relative order and follow the built-ins.

    Returns:
        JSON Response: the reset key order on success.

    Raises:
        403: CSRF token validation failed.
        500: Failed to write the order file.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    ordered = set_order(_default_template_order())
    try:
        _save_template_order(ordered)
    except OSError as e:
        return jsonify(
            {"status": "error", "message": f"Failed to save template order: {e}"}
        ), 500
    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("Template order reset to default: %d templates", len(ordered))
    return jsonify({"status": "ok", "order": ordered})


@app.route("/api/templates/delete", methods=["POST"])
def api_delete_template() -> Any:
    """Delete a custom template (unregister it and remove the on-disk source).

    Returns:
        JSON Response: the deleted key on success.

    Raises:
        400: Invalid request format or an attempt to delete a built-in.
        403: CSRF token validation failed.
        404: Template not found.
        500: Failed to delete the template file.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400
    key = str(data.get("key", "")).strip()
    if not key:
        return jsonify(
            {"status": "error", "message": "Select a template to delete"}
        ), 400
    registered_keys = [item["key"] for item in list_dicts()]
    if key not in registered_keys:
        return jsonify({"status": "error", "message": "Template not found"}), 404
    if not key.startswith("custom_"):
        return jsonify(
            {"status": "error", "message": "Built-in templates cannot be deleted"}
        ), 400
    for directory in (_custom_templates_dir(), _legacy_custom_templates_dir()):
        if directory is None:
            continue
        path = directory / f"{key}.py"
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError as e:
            return jsonify(
                {"status": "error", "message": f"Failed to delete template file: {e}"}
            ), 500
    unregister(key)
    sys.modules.pop(f"src.templates.{key}", None)
    try:
        _save_template_order([item["key"] for item in list_dicts()])
    except OSError as e:
        logger.warning("Failed to save template order after deleting a template: %s", e)
    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("Custom template deleted: %s", key)
    return jsonify({"status": "ok", "key": key, "count": len(list_dicts())})


def _template_source_code(base_key: str, template: Any) -> str:
    """Return the source code of a source template for AI rewriting.

    Custom templates prefer the on-disk source file; when it is missing,
    equivalent source is rebuilt from the template spec. Built-in templates
    return the template class source plus helper functions/constants defined
    in the same module, so the AI can understand rule code such as
    three-ping-tails, isolated-ping, and step patterns.

    Args:
        base_key: Source template key.
        template: Source template object (PoetryTemplate instance).

    Returns:
        Source text; empty string when unavailable.
    """
    if base_key.startswith("custom_"):
        for directory in (_custom_templates_dir(), _legacy_custom_templates_dir()):
            if directory is None:
                continue
            path = directory / f"{base_key}.py"
            if not path.exists():
                continue
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                continue
        try:
            data = template.to_dict()
            from src.templates.convert import convert_syllable_count

            alternatives = list(
                data.get("syllable_constraint_alternatives")
                or [data.get("syllable_constraints") or []]
            )
            syllables = [
                convert_syllable_count(item)
                for item in data.get("syllables_per_line") or []
            ]
            language = str(data.get("language", ""))
            dimension, _ = custom_template_schemes().get(language, ("", ()))
            safe_name = base_key[len("custom_") :]
            return _build_custom_template_code(
                name=str(data.get("name", "")),
                language=language,
                lines=len(syllables),
                syllables_per_line=syllables,
                dimension=dimension,
                constraints=list(alternatives[0]),
                custom_code=str(data.get("custom_code", "")),
                class_name=f"Custom{safe_name.title().replace('_', '')}Template",
                file_key=base_key,
                alternatives=alternatives,
                rhyme_scheme=str(data.get("rhyme_scheme", "")),
                rhyme_distinct=bool(data.get("rhyme_distinct", False)),
                structural_rules=data.get("structural_rules"),
                rule_note=str(data.get("rule_note", "")),
            )
        except Exception as e:  # noqa: BLE001 - source rebuild: AI reference only
            logger.warning(
                "Failed to rebuild custom template source %s: %s", base_key, e
            )
            return ""

    class_object = type(template)
    parts: list[str] = []
    try:
        parts.append(inspect.getsource(class_object))
    except OSError, TypeError:
        return ""
    module = sys.modules.get(class_object.__module__)
    if module is not None:
        for name, obj in vars(module).items():
            if inspect.isfunction(obj):
                if getattr(obj, "__module__", None) != module.__name__:
                    continue
                try:
                    parts.append(inspect.getsource(obj))
                except OSError, TypeError:
                    continue
            elif (
                name.startswith("_")
                and not name.startswith("__")
                and isinstance(obj, (dict, frozenset, tuple, list, set))
            ):
                parts.append(f"{name} = {obj!r}")
    return "\n\n".join(parts)


@app.route("/api/templates/convert", methods=["POST"])
def api_convert_template() -> Any:
    """Unified cross-language template conversion endpoint.

    Reads the source template's full spec (line count / syllables per line /
    per-position constraints / rhyme scheme / custom code) and converts only
    the per-position constraint attribute values into target-language values
    according to the mapping; everything else is copied verbatim. The
    frontend "apply conversion" action and the template editor AI's
    set_from_template tool share this implementation.

    Returns:
        JSON Response: the converted template spec on success; an error
        message on failure.

    Raises:
        400: Invalid request format, unknown template/language, or an
            invalid mapping.
        403: CSRF token validation failed.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400
    base_key = str(data.get("base_template_key", "")).strip()
    language = str(data.get("language", ""))
    if not base_key:
        return jsonify({"status": "error", "message": "Select a source template"}), 400
    from src.templates.convert import convert_template

    spec, error = convert_template(base_key, language, data.get("mapping"))
    if error:
        return jsonify({"status": "error", "message": error}), 400

    if bool(data.get("ai_rewrite_code", False)):
        spec["ai_rewrite_requested"] = True
        spec["ai_rewrite_applied"] = False
        ai_error = ""
        try:
            from src.agents.editor_ai import TemplateCodeRewriter
            from src.config import get_config
            from src.templates import get as get_template

            editor_config = get_config().editor
            if not editor_config.get("api_key"):
                ai_error = (
                    "Template AI is not configured; set a template AI API key "
                    "in Settings first"
                )
            else:
                source_template = get_template(base_key)
                source_code = _template_source_code(base_key, source_template)
                if not source_code:
                    ai_error = "Unable to get source template code; AI rewrite skipped"
                else:
                    rewritten = TemplateCodeRewriter(editor_config).rewrite(
                        source_language=str(spec.get("source_language", "")),
                        target_language=language,
                        mapping=dict(spec.get("mapped") or {}),
                        source_code=source_code,
                        target_spec=spec,
                        rule_note=str(spec.get("rule_note", "") or ""),
                    )
                    if rewritten.get("status") == "ok":
                        spec["code"] = str(rewritten.get("code", ""))
                        spec["ai_rewrite_applied"] = True
                        spec["ai_rewrite_notes"] = str(rewritten.get("notes", ""))
                        carried = list(spec.get("carried_rules") or [])
                        if "ai_code" not in carried:
                            carried.append("ai_code")
                        spec["carried_rules"] = carried
                    else:
                        ai_error = str(
                            rewritten.get("message", "Template code rewrite failed")
                        )
        except Exception as e:  # noqa: BLE001 - AI rewrite: deterministic fallback
            ai_error = f"Template code AI rewrite failed: {e}"
        if ai_error:
            spec["ai_rewrite_error"] = ai_error
    return jsonify(spec)


@app.route("/api/config", methods=["GET"])
def api_get_config() -> Any:
    """Read the LLM configuration.

    Returns:
        JSON Response with the writer and checker endpoint configs.

    Raises:
        403: CSRF token validation failed.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    from src.config import get_config

    config = get_config()
    return jsonify(
        {
            "writer": config.writer,
            "checker": config.checker,
            "editor": config.editor,
            "language": config.language,
        }
    )


@app.route("/api/config", methods=["POST"])
def api_save_config() -> Any:
    """Save the LLM configuration.

    Returns:
        JSON Response (success or error).

    Raises:
        400: Invalid request format.
        403: CSRF token validation failed.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403
    from src.config import get_config

    config = get_config()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400
    for key in ("writer", "checker", "editor"):
        if key in data:
            value = data[key]
            if not isinstance(value, dict):
                return jsonify(
                    {"status": "error", "message": f"Invalid format for {key} config"}
                ), 400
            config.__setattr__(key, value)
    if "language" in data:
        lang = data["language"]
        if lang in ("zh", "en"):
            config.language = lang
    config.save()
    logger.info(
        "LLM configuration saved (writer.base_url=%s, checker.base_url=%s, "
        "editor.base_url=%s)",
        config.writer["base_url"],
        config.checker["base_url"],
        config.editor["base_url"],
    )
    _llm_status["writer"] = "unknown"
    _llm_status["checker"] = "unknown"
    _llm_status["editor"] = "unknown"
    _llm_ping_event.set()
    return jsonify({"status": "ok"})


@socketio.on("connect")
def handle_connect() -> None:
    """Socket connection established.

    No return value and no side effects.
    """


def _emit_done(session_id: str, result: Any) -> None:
    """Push a done event to the session.

    Args:
        session_id: SocketIO session ID.
        result: Pipeline result state.

    """
    socketio.emit(
        "done",
        {
            "draft": result.draft,
            "final_poem": result.final_poem,
            "title": result.title,
            "formatted_poem": result.formatted_poem,
            "language": str(result.template.get("language", "")),
            "centered": bool(result.template.get("centered", True)),
            "checker_pass": result.checker_pass,
            "checker_suggestions": result.checker_suggestions,
            "step_details": result.step_details,
        },
        to=session_id,
    )


@socketio.on("generate")
def handle_generate(data: dict[str, Any]) -> None:
    """Start generation: run the four-step pipeline in a background thread.

    Args:
        data: Event payload (topic, template_key).

    """
    from src.pipeline.pipeline import PoetryPipeline

    topic = str(data.get("topic", ""))
    template_key = str(data.get("template_key", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # socketio

    if not topic or not template_key:
        emit("error", {"message": "Topic and template must not be empty"})
        return

    logger.info(
        "generate started session=%s template=%s topic=%r",
        session_id,
        template_key,
        topic,
    )
    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """Push pipeline progress to the session.

        Args:
            state_dict: Pipeline state dictionary.

        """
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        """Run the four-step pipeline in a background thread and emit events."""
        try:
            result = pipeline.run(
                topic=topic,
                template_key=template_key,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - generation thread: emit error
            logger.error("generate failed session=%s: %s", session_id, e)
            socketio.emit(
                "error", {"message": f"Generation failed: {e}"}, to=session_id
            )
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "generate finished session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("feedback")
def handle_feedback(data: dict[str, Any]) -> None:
    """Continue from user feedback: re-run Step 3 polishing with it.

    Args:
        data: Event payload (user feedback text).

    """
    from src.pipeline.pipeline import PoetryPipeline

    feedback = str(data.get("feedback", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # socketio

    session_data = _active_states.get(session_id, {})
    pipeline_state = session_data.get("pipeline_state")
    if pipeline_state is None:
        emit(
            "error", {"message": "No active generation session; generate a poem first"}
        )
        return

    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """Push pipeline progress to the session.

        Args:
            state_dict: Pipeline state dictionary.

        """
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        """Re-run the pipeline in a background thread and emit events."""
        try:
            result = pipeline.continue_with_feedback(
                state=pipeline_state,
                user_feedback=feedback,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - feedback thread: emit error
            logger.error("feedback failed session=%s: %s", session_id, e)
            socketio.emit(
                "error", {"message": f"Feedback processing failed: {e}"}, to=session_id
            )
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "feedback finished session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


def _sequence_payload(state: Any) -> dict[str, Any]:
    """Convert the poem-sequence state into a serializable dictionary.

    Args:
        state: SequenceState.

    Returns:
        Sequence dictionary usable by the frontend.

    """
    return {
        "title": state.title,
        "plan_text": state.plan_text,
        "plan_completed": state.plan_completed,
        "completed": state.completed,
        "ok": state.ok,
        "poems": [
            {
                "title": p.final_title or p.title,
                "planned_title": p.title,
                "template_key": p.template_key,
                "language": p.language,
                "centered": p.centered,
                "prompt": p.prompt,
                "draft": list(p.draft),
                "checker_pass": p.checker_pass,
                "checker_suggestions": p.checker_suggestions,
                "formatted_poem": p.formatted_poem,
                "rounds": p.rounds,
                "done": p.done,
            }
            for p in state.poems
        ],
    }


@socketio.on("generate_sequence")
def handle_generate_sequence(data: dict[str, Any]) -> None:
    """Start sequence generation: plan → generate/check each poem → assemble.

    Args:
        data: Event payload (topic = overall goal; template_keys = meters).

    """
    from src.pipeline.sequence import PoemSequencePipeline

    topic = str(data.get("topic", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # socketio

    if not topic:
        emit("error", {"message": "Sequence topic must not be empty"})
        return

    template_keys: list[str] | None = None
    if "template_keys" in data:
        raw = data.get("template_keys")
        if not isinstance(raw, list) or not raw:
            emit("error", {"message": "Select a meter for each poem"})
            return
        template_keys = [str(item) for item in raw]

    logger.info("generate_sequence started session=%s topic=%r", session_id, topic)
    pipeline = PoemSequencePipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """Push sequence planning/generation progress to the session.

        Args:
            state_dict: Sequence state dictionary.

        """
        socketio.emit("sequence_progress", state_dict, to=session_id)

    def run() -> None:
        """Run the sequence pipeline in a background thread and emit events."""
        try:
            state = pipeline.run(
                topic, on_progress=on_progress, template_keys=template_keys
            )
        except Exception as e:  # noqa: BLE001 - sequence thread: emit error
            logger.error("generate_sequence failed session=%s: %s", session_id, e)
            socketio.emit(
                "error", {"message": f"Sequence generation failed: {e}"}, to=session_id
            )
            return
        _active_sequences[session_id] = {"sequence_state": state}
        logger.info(
            "generate_sequence finished session=%s poems=%s ok=%s",
            session_id,
            len(state.poems),
            state.ok,
        )
        socketio.emit("sequence_done", _sequence_payload(state), to=session_id)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Disconnect: clean up the session state."""
    _active_states.pop(request.sid, None)  # type: ignore[attr-defined]  # socketio
    _active_sequences.pop(request.sid, None)  # type: ignore[attr-defined]  # socketio


def _render_constraint_table(constraints: list[Any]) -> str:
    """Render one per-position constraint table as Python literal source.

    Args:
        constraints: Per-position constraints (line -> cell -> {attributes}).

    Returns:
        Python list literal source.

    """
    constraints_code: list[str] = []
    for line_c in constraints:
        cells: list[str] = []
        for c in line_c if isinstance(line_c, list) else []:
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            non_empty = {k: str(v) for k, v in attrs.items() if v}
            if non_empty:
                rendered = json.dumps(non_empty, ensure_ascii=False)
                cells.append(f"_make_syl(attributes={rendered})")
            else:
                cells.append("_make_syl()")
        constraints_code.append("[" + ", ".join(cells) + "]")
    if not constraints_code:
        return "[]"
    return "[\n            " + ",\n            ".join(constraints_code) + "\n        ]"


def _build_custom_template_code(
    name: str,
    language: str,
    lines: int,
    syllables_per_line: list[int],
    dimension: str,
    constraints: list[Any],
    custom_code: str,
    class_name: str,
    file_key: str,
    alternatives: list[Any] | None = None,
    rhyme_scheme: str = "",
    rhyme_distinct: bool = False,
    structural_rules: dict[str, Any] | None = None,
    rule_note: str = "",
) -> str:
    """Generate Python source for a custom template (written to disk).

    Args:
        name: Template display name.
        language: Language code (zh/en/fr/it/la).
        lines: Number of lines.
        syllables_per_line: Syllables per line.
        dimension: Per-position constraint attribute key ("" = none).
        constraints: Per-position constraints (line -> cell -> {attributes}).
        custom_code: Extra validate_full code supplied by the user.
        class_name: Generated template class name.
        file_key: Registration key (custom_<name>).
        alternatives: Multiple constraint tables (any one suffices);
            constraints is used when empty.
        rhyme_scheme: Normalized rhyme scheme (e.g. "ABABCDCDEFEFGG"; empty
            means no rhyme).
        rhyme_distinct: Whether distinct rhyme groups must all differ.
        structural_rules: Materialized structural rules (e.g. jinti tone
            skeleton / three-ping-tails / isolated-ping).
        rule_note: User-written template rule description (given to the
            writer AI as a prompt).

    Returns:
        Source text that can be written directly to
        src/templates/custom_*.py.

    """
    tables: list[Any] = (
        list(alternatives)
        if alternatives
        else ([list(constraints)] if constraints else [])
    )
    if not tables:
        tables = [[]]
    rendered_tables = [_render_constraint_table(list(table or [])) for table in tables]

    # REUSE header for the generated file. The SPDX tag is split and joined so
    # this file never contains a contiguous literal that REUSE would
    # misinterpret as a license expression (reuse lint reports it invalid).
    spdx_line = "# SPDX-License-" + "Identifier: MIT"
    # With materialized structural rules, rhyme and structure are checked by
    # check_jinti_rules together to avoid duplication.
    rhyme_import = (
        "from .rhyme import check_rhyme_scheme\n"
        if rhyme_scheme and not structural_rules
        else ""
    )
    structural_import = (
        "from .structural import check_jinti_rules\n" if structural_rules else ""
    )
    rule_parts = [
        (
            f"自定义格律模板：共 {lines} 行，"
            f"每行音节数依次为 {', '.join(str(s) for s in syllables_per_line)}"
        )
    ]
    if len(tables) > 1:
        rule_parts.append(f"共 {len(tables)} 种可选音节约束，满足任意一种即可")
    from src.templates.rhyme import rhyme_scheme_description

    rhyme_desc = rhyme_scheme_description(rhyme_scheme)
    if rhyme_desc:
        rule_parts.append(
            rhyme_desc + ("（不同韵组须互不相同）" if rhyme_distinct else "")
        )
    if structural_rules:
        rule_parts.append("近体诗结构规则（平仄骨架/三平尾/孤平/押韵）随转化保留")
    rule_description = "；".join(rule_parts) + "。"
    code_body = (
        f"# Copyright (c) 2026 xhdlphzr\n"
        f"{spdx_line}\n"
        f"# Auto-generated custom template: {name}\n\n"
        f"from . import PoetryTemplate, _make_syl, register\n"
        f"from . import {language} as rules\n"
        f"{rhyme_import}{structural_import}\n"
        f"class {class_name}(PoetryTemplate):\n"
        f"    name = {json.dumps(name, ensure_ascii=False)}\n"
        f'    language = "{language}"\n'
        f"    lines = {lines}\n"
        f"    syllables_per_line = {syllables_per_line}\n"
        f"    rhyme_scheme = {json.dumps(rhyme_scheme, ensure_ascii=False)}\n"
        f"    rhyme_distinct = {rhyme_distinct!r}\n"
        f"    custom_code = {json.dumps(custom_code, ensure_ascii=False)}\n"
        f"    structural_rules = {structural_rules!r}\n"
        f"    rule_note = {json.dumps(rule_note, ensure_ascii=False)}\n"
        f"    rule_description = {json.dumps(rule_description, ensure_ascii=False)}\n\n"
        f"    def get_syllable_constraints(self):\n"
        f"        return {rendered_tables[0]}\n\n"
    )
    if len(rendered_tables) > 1:
        alternatives_str = (
            "[\n"
            + ",\n".join("            " + table for table in rendered_tables)
            + "\n        ]"
        )
        code_body += (
            "    def get_syllable_constraint_alternatives(self):\n"
            f"        return {alternatives_str}\n\n"
        )
    code_body += "    def validate_full(self, poem, syllables):\n        errors = []\n"
    if structural_rules:
        code_body += (
            f"        errors.extend(\n"
            f"            check_jinti_rules(\n"
            f"                {json.dumps(language, ensure_ascii=False)},\n"
            f"                poem,\n"
            f"                syllables,\n"
            f"                self.structural_rules,\n"
            f"            )\n"
            f"        )\n"
        )
    elif rhyme_scheme:
        code_body += (
            f"        errors.extend(\n"
            f"            check_rhyme_scheme(\n"
            f"                {json.dumps(language, ensure_ascii=False)},\n"
            f"                poem,\n"
            f"                {json.dumps(rhyme_scheme, ensure_ascii=False)},\n"
            f"                distinct={rhyme_distinct!r},\n"
            f"                syllables=syllables,\n"
            f"            )\n"
            f"        )\n"
        )
    if custom_code:
        for line in custom_code.split("\n"):
            if line.strip():
                code_body += f"        {line}\n"
    code_body += "        return errors\n\n\n"
    code_body += f"def register_custom_{file_key.replace('custom_', '')}():\n"
    code_body += f'    register("{file_key}", {class_name}())\n'
    return code_body


def _create_custom_template(
    name: str,
    language: str,
    lines: int,
    syllables_per_line: list[int],
    alternatives: list[Any],
    custom_code: str,
    rhyme_scheme: str = "",
    rhyme_distinct: bool = False,
    structural_rules: dict[str, Any] | None = None,
    rule_note: str = "",
) -> tuple[int, dict[str, Any]]:
    """Persist a custom template and hot-register it.

    Args:
        name: Template display name.
        language: Language code.
        lines: Number of lines.
        syllables_per_line: Syllables per line.
        alternatives: Multiple per-position constraint tables.
        custom_code: Custom whole-poem validation code.
        rhyme_scheme: Normalized rhyme scheme.
        rhyme_distinct: Whether distinct rhyme groups must all differ.
        structural_rules: Materialized structural rules (optional).
        rule_note: User-written template rule description (optional; prompt
            for the writer AI).

    Returns:
        (HTTP status code, response payload); success includes the key.

    """
    import re

    safe_name = re.sub(r"\W+", "_", name).strip("_")
    if not safe_name:
        return 400, {
            "status": "error",
            "message": (
                "Template name must contain letters or digits (cannot form "
                "a valid identifier)"
            ),
        }

    from src.templates.rhyme import normalize_rhyme_scheme
    from src.templates.structural import normalize_structural_rules

    rhyme_scheme, rhyme_error = normalize_rhyme_scheme(rhyme_scheme, lines)
    if rhyme_error:
        return 400, {"status": "error", "message": rhyme_error}
    structural, structural_error = normalize_structural_rules(structural_rules)
    if structural_error:
        return 400, {"status": "error", "message": structural_error}

    class_name = f"Custom{safe_name.title().replace('_', '')}Template"
    file_key = f"custom_{safe_name}"
    file_path = _custom_templates_dir() / f"{file_key}.py"

    dimension, _value_options = custom_template_schemes().get(language, ("", ()))
    code_body = _build_custom_template_code(
        name=name,
        language=language,
        lines=lines,
        syllables_per_line=syllables_per_line,
        dimension=dimension,
        constraints=list(alternatives[0]) if alternatives else [],
        custom_code=custom_code,
        class_name=class_name,
        file_key=file_key,
        alternatives=list(alternatives),
        rhyme_scheme=rhyme_scheme,
        rhyme_distinct=rhyme_distinct,
        structural_rules=structural,
        rule_note=rule_note,
    )

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code_body, encoding="utf-8")
    except OSError as e:
        return 500, {
            "status": "error",
            "message": f"Failed to write template file: {e}",
        }

    try:
        module = _load_custom_template_module(file_path)
        reg_func = getattr(module, f"register_custom_{safe_name}", None)
        if reg_func:
            reg_func()
    except Exception as e:  # noqa: BLE001 - template registration error -> 500
        return 500, {"status": "error", "message": f"Template registration failed: {e}"}

    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("Custom template created: %s (%s, %d lines)", name, language, lines)
    return 200, {
        "status": "ok",
        "message": f"Template '{name}' created and registered",
        "count": len(list_dicts()),
        "key": file_key,
    }


def _create_custom_template_from_draft(
    draft: Any,
) -> tuple[int, dict[str, Any]]:
    """Persist and register the template editor AI's draft.

    Args:
        draft: TemplateDraft instance.

    Returns:
        (HTTP status code, response payload).

    """
    return _create_custom_template(
        name=str(draft.name),
        language=str(draft.language),
        lines=int(draft.lines),
        syllables_per_line=list(draft.syllables_per_line),
        alternatives=[list(table) for table in draft.constraint_tables()],
        custom_code=str(draft.code),
        rhyme_scheme=str(draft.rhyme_scheme),
        rhyme_distinct=bool(draft.rhyme_distinct),
        structural_rules=(
            dict(draft.structural_rules) if draft.structural_rules else None
        ),
        rule_note=str(draft.rule_note),
    )


@app.route("/api/templates/custom", methods=["POST"])
def api_create_custom_template() -> Any:
    """Create a custom metrical template (persisted and hot-registered).

    The template is written as src/templates/custom_*.py.

    Returns:
        JSON Response (template key on success, or an error message).

    Raises:
        400: Invalid request format or invalid template code.
        403: CSRF token validation failed.

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400
    name = str(data.get("name", "")).strip()
    language = str(data.get("language", "zh"))
    try:
        lines = int(data.get("lines", 4))
    except TypeError, ValueError:
        lines = 4
    lines = max(1, min(lines, 30))
    syllables_per_line = data.get("syllables_per_line", [5] * lines)
    raw_constraints = data.get("constraints", [])
    constraints = raw_constraints if isinstance(raw_constraints, list) else []
    custom_code = str(data.get("code", "")).strip()

    if not name:
        return jsonify(
            {"status": "error", "message": "Template name must not be empty"}
        ), 400
    schemes = custom_template_schemes()
    if language not in schemes:
        return jsonify({"status": "error", "message": "Unsupported language"}), 400
    try:
        syllables_per_line = [max(1, int(s)) for s in syllables_per_line][:lines]
    except TypeError, ValueError:
        return jsonify(
            {"status": "error", "message": "Invalid syllables-per-line format"}
        ), 400
    if len(syllables_per_line) != lines:
        return jsonify(
            {
                "status": "error",
                "message": "Syllables list length must equal the number of lines",
            }
        ), 400

    raw_alternatives = data.get("alternatives")
    if isinstance(raw_alternatives, list) and raw_alternatives:
        alternatives = [
            table if isinstance(table, list) else [] for table in raw_alternatives
        ]
    else:
        alternatives = [constraints]

    from src.templates.rhyme import normalize_rhyme_scheme

    rhyme_scheme, rhyme_error = normalize_rhyme_scheme(
        str(data.get("rhyme_scheme", "")), lines
    )
    if rhyme_error:
        return jsonify({"status": "error", "message": rhyme_error}), 400
    rhyme_distinct = bool(data.get("rhyme_distinct", False))
    raw_structural = data.get("structural_rules")
    structural_rules = raw_structural if isinstance(raw_structural, dict) else None
    rule_note = str(data.get("rule_note", "") or "").strip()
    if len(rule_note) > 4000:
        return jsonify(
            {
                "status": "error",
                "message": "Template rule description must not exceed 4000 characters",
            }
        ), 400

    status, payload = _create_custom_template(
        name=name,
        language=language,
        lines=lines,
        syllables_per_line=syllables_per_line,
        alternatives=alternatives,
        custom_code=custom_code,
        rhyme_scheme=rhyme_scheme,
        rhyme_distinct=rhyme_distinct,
        structural_rules=structural_rules,
        rule_note=rule_note,
    )
    return jsonify(payload), status


@socketio.on("edit_template")
def handle_edit_template(data: dict[str, Any]) -> None:
    """Template editor AI: configure the template in a background thread.

    Thoughts, answers, and tool calls are streamed to the frontend.

    Args:
        data: Event payload (prompt = description; draft = current draft).

    """
    from src.agents.editor_ai import TemplateEditorAI
    from src.config import get_config

    prompt = str(data.get("prompt", "")).strip()
    raw_draft = data.get("draft")
    draft_payload = raw_draft if isinstance(raw_draft, dict) else {}
    session_id = request.sid  # type: ignore[attr-defined]  # socketio

    if not prompt:
        socketio.emit(
            "template_ai_done",
            {"status": "error", "message": "Describe the template you want first"},
            to=session_id,
        )
        return

    editor_config = get_config().editor
    if not editor_config.get("api_key"):
        socketio.emit(
            "template_ai_done",
            {
                "status": "error",
                "message": (
                    "Template AI is not configured; set a template AI API key "
                    "in Settings first"
                ),
            },
            to=session_id,
        )
        return

    logger.info("edit_template started session=%s prompt=%r", session_id, prompt)

    def run() -> None:
        """Run the template editor AI in a background thread and push events."""
        try:
            agent = TemplateEditorAI(editor_config)

            def on_event(event: dict[str, Any]) -> None:
                """Push one template-AI event to the session.

                Args:
                    event: Event dictionary.

                """
                socketio.emit("template_ai", event, to=session_id)

            result = agent.edit(prompt, draft_payload, emit=on_event)
        except Exception as e:  # noqa: BLE001 - template-AI thread: emit error
            logger.error("edit_template failed session=%s: %s", session_id, e)
            socketio.emit(
                "template_ai_done",
                {"status": "error", "message": f"Template AI processing failed: {e}"},
                to=session_id,
            )
            return

        draft_result = result.draft.to_payload()
        if not result.submitted:
            socketio.emit(
                "template_ai_done",
                {
                    "status": "ok",
                    "draft": draft_result,
                    "created_key": None,
                    "message": result.message,
                },
                to=session_id,
            )
            return

        status, body = _create_custom_template_from_draft(result.draft)
        if status == 200:
            logger.info("Template AI created template: %s", body.get("key"))
            socketio.emit(
                "template_ai_done",
                {
                    "status": "ok",
                    "draft": draft_result,
                    "created_key": body.get("key"),
                    "message": str(body.get("message", "")),
                },
                to=session_id,
            )
        else:
            socketio.emit(
                "template_ai_done",
                {
                    "status": "error",
                    "draft": draft_result,
                    "message": str(body.get("message", "Template creation failed")),
                },
                to=session_id,
            )

    threading.Thread(target=run, daemon=True).start()


_HISTORY_DB_PATH: Path | None = None


def set_history_db_path(path: Path) -> None:
    """Override the history database path (mainly for tests).

    Args:
        path: New database file path.

    """
    global _HISTORY_DB_PATH
    _HISTORY_DB_PATH = path


def get_history_db_path() -> Path:
    """Return the history database path (default ~/.stanza_weaver/history.db).

    Returns:
        Database file path.

    """
    global _HISTORY_DB_PATH
    if _HISTORY_DB_PATH is None:
        _HISTORY_DB_PATH = Path.home() / ".stanza_weaver" / "history.db"
    return _HISTORY_DB_PATH


def _init_history_db() -> None:
    """Initialize the history table (idempotent)."""
    import sqlite3

    hdb = get_history_db_path()
    hdb.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(hdb))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        template_name TEXT,
        poem TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )"""
    )
    conn.commit()
    conn.close()


@app.route("/api/history", methods=["GET"])
def api_get_history() -> Any:
    """Read history records (latest 50).

    Returns:
        JSON Response, list of history records.

    """
    import sqlite3

    _init_history_db()
    hdb = get_history_db_path()
    conn = sqlite3.connect(str(hdb))
    rows = conn.execute(
        "SELECT id, topic, template_name, poem, created_at FROM history ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify(
        [
            {
                "id": r[0],
                "topic": r[1],
                "template_name": r[2],
                "poem": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
    )


@app.route("/api/history", methods=["POST"])
def api_save_history() -> Any:
    """Save a history record (called by the frontend after the final draft).

    Returns:
        JSON Response (success or error).

    Raises:
        400: Invalid request format.
        403: CSRF token validation failed.

    """
    import sqlite3

    if not _require_csrf():
        return jsonify({"status": "error", "message": "Missing security token"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid request format"}), 400

    _init_history_db()
    hdb = get_history_db_path()
    conn = sqlite3.connect(str(hdb))
    conn.execute(
        "INSERT INTO history (topic, template_name, poem) VALUES (?, ?, ?)",
        (
            str(data.get("topic", "")),
            str(data.get("template_name", "")),
            str(data.get("poem", "")),
        ),
    )
    conn.commit()
    conn.close()
    logger.info(
        "History record saved: %s (%s)",
        data.get("template_name", ""),
        data.get("topic", ""),
    )
    return jsonify({"status": "ok"})


def start_server() -> None:
    """Start the SocketIO service.

    The listen address/port can be overridden with the STANZAWEAVER_HOST /
    STANZAWEAVER_PORT environment variables (for Docker deployments set
    STANZAWEAVER_HOST=0.0.0.0 together with port mapping).
    """
    host = os.environ.get("STANZAWEAVER_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("STANZAWEAVER_PORT", "5000"))
    except ValueError:
        port = 5000
    logger.info("[StanzaWeaver] Server started at http://%s:%s", host, port)
    _start_background_threads()
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)


def main() -> None:
    """Entry point: prefer the pywebview window, else a plain HTTP service.

    If desktop-window initialization fails (e.g. no display environment or
    missing GUI libraries), fall back to the HTTP service automatically so
    headless environments such as Docker keep working.

    Returns:
        None.

    """
    try:
        import webview
    except ImportError:
        start_server()
        return

    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    try:
        webview.create_window(
            "StanzaWeaver",
            "http://127.0.0.1:5000",
            width=900,
            height=700,
            min_size=(700, 500),
        )
        webview.start()
    except Exception as e:  # noqa: BLE001 - GUI-init fallback: use HTTP
        logger.warning("GUI initialization failed; falling back to HTTP mode: %s", e)
        t.join()


if __name__ == "__main__":
    main()
