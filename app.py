# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""StanzaWeaver 应用入口（Flask + SocketIO + pywebview）.

- HTTP API：模板列表、LLM 配置、历史记录、自定义模板、导入状态；
- SocketIO：generate / feedback 事件驱动四步流水线，progress/done/error 推送；
- 安全：仅限本机访问（Host 校验）+ CSRF 令牌保护写接口；
- 首次运行自动导入词库（后台线程）。
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

_vocab_importing = True


def _auto_import() -> None:
    """后台线程：首次运行自动导入词库."""
    global _vocab_importing
    from src.knowledge.vocabulary import init_db

    try:
        init_db()
        logger.info("[StanzaWeaver] 检查词库...")
        from src.knowledge.importer import import_all

        import_all()
    except Exception as e:  # noqa: BLE001 - 词库导入兜底：失败仅记录，不影响启动
        logger.error("[StanzaWeaver] 词库导入失败: %s", e)
    finally:
        _vocab_importing = False
        _llm_ping_event.set()


def _ping_one_endpoint(endpoint_name: str) -> None:
    """探测单个 LLM 端点连通性.

    Args:
        endpoint_name: 端点名称（"writer" / "checker" / "editor"）。

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
    except Exception:  # noqa: BLE001 - ping 兜底
        _llm_status[endpoint_name] = "error"


def _auto_ping() -> None:
    """后台线程：启动时探测一次 LLM 端点，之后仅在配置保存/词库导入后重探.

    不再定时轮询：避免用户点击"取消设置"等操作后被误认为重新检测连接性；
    连通性只在保存配置（或词库导入完成、手动点击检查）时刷新。
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
    """按需启动后台导入/连通性探测线程.

    仅在 ``start_server`` 启动 HTTP 服务时调用；测试环境下不启动（由
    conftest 注入 STANZA_WEAVER_TEST=1），避免异步线程读取被测试重定向的
    数据库路径而污染临时词库，也避免仅 import app 就发起网络请求。
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


#: 环境变量：覆盖自定义模板目录（Docker/便携部署可指向持久化目录）。
_CUSTOM_TEMPLATES_DIR_ENV = "STANZAWEAVER_TEMPLATES_DIR"


def _custom_templates_dir() -> Path:
    """返回自定义模板文件所在目录.

    源码运行时使用仓库内的 ``src/templates``（开发方便）；PyInstaller 编译版
    的程序目录通常不可写、且升级会整体替换，因此改用用户数据目录
    ``~/.stanza_weaver/templates``。可用 ``STANZAWEAVER_TEMPLATES_DIR`` 覆盖。

    Returns:
        自定义模板目录路径（不保证已存在）。

    """
    override = os.environ.get(_CUSTOM_TEMPLATES_DIR_ENV, "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path.home() / ".stanza_weaver" / "templates"
    return Path(__file__).parent / "src" / "templates"


def _legacy_custom_templates_dir() -> Path | None:
    """返回编译版旧版本的自定义模板目录（安装目录内，用于兼容/迁移）.

    Returns:
        旧目录路径；源码模式或与新目录相同时返回 None。

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
    """把旧版本安装目录内的自定义模板复制到新目录（已存在则跳过）.

    Args:
        primary: 新的自定义模板目录。
        legacy: 旧模板目录（可为 None）。

    """
    if legacy is None or not legacy.exists():
        return
    try:
        primary.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("[StanzaWeaver] 自定义模板目录创建失败 %s: %s", primary, e)
        return
    for f in sorted(legacy.glob("custom_*.py")):
        dest = primary / f.name
        if dest.exists():
            continue
        try:
            shutil.copy2(f, dest)
            logger.info("[StanzaWeaver] 已迁移自定义模板 %s -> %s", f.name, primary)
        except OSError as e:
            logger.warning("[StanzaWeaver] 自定义模板迁移失败 %s: %s", f.name, e)


def _load_custom_template_module(file_path: Path) -> Any:
    """从文件加载自定义模板模块（支持编译版的用户数据目录）.

    生成的模板通过相对导入复用 ``src.templates`` 包内的基类与语言模块，
    因此模块名固定为 ``src.templates.<文件名>``，与模块所在目录无关。

    Args:
        file_path: 模板源码文件路径。

    Returns:
        已执行的模块对象。

    Raises:
        ImportError: 无法为文件创建有效的模块规格。

    """
    module_name = f"src.templates.{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模板模块: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def _register_custom_templates() -> None:
    """注册自定义模板（重启自动恢复）.

    源码模式读取 ``src/templates``；编译版读取用户数据目录，并兼容迁移
    旧版安装目录（``_internal/src/templates``）内的模板。旧目录先加载、
    新目录后加载，同名模板以用户目录版本为准。
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
            except Exception as e:  # noqa: BLE001 - 自定义模板可含任意用户代码，注册失败仅记录
                logger.error("[StanzaWeaver] 自定义模板注册失败 %s: %s", f.name, e)


def _template_order_path() -> Path:
    """用户自定义模板顺序的持久化文件路径.

    Returns:
        ``~/.stanza_weaver/template_order.json``。

    """
    return Path.home() / ".stanza_weaver" / "template_order.json"


def _load_template_order() -> list[str]:
    """读取已保存的模板顺序.

    Returns:
        key 列表；文件不存在/损坏/格式非法时返回空列表。

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
    """把模板顺序写入用户数据目录.

    Args:
        keys: 按显示顺序排列的模板 key 列表。

    Raises:
        OSError: 写入失败时抛出，由调用方决定是否回报错误。

    """
    path = _template_order_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(list(keys), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _apply_saved_template_order() -> None:
    """启动时应用已保存的模板顺序（测试环境跳过，避免外部数据影响测试）."""
    if os.environ.get("STANZA_WEAVER_TEST") == "1":
        return
    keys = _load_template_order()
    if keys:
        set_order(keys)


_register_custom_templates()
_apply_saved_template_order()


@app.before_request
def _guard_local_access() -> Any:
    """仅允许本机访问（Host 校验）.

    Returns:
        None 表示通过；jsonify Response 表示拒绝（403）。

    """
    host = request.host or ""
    if not host.startswith(("127.0.0.1", "localhost")):
        return jsonify({"status": "error", "message": "拒绝非本机访问"}), 403
    return None


def _require_csrf() -> bool:
    """校验 CSRF 令牌.

    Returns:
        令牌匹配返回 True。

    """
    return request.headers.get("X-CSRF-Token", "") == _CSRF_TOKEN


@app.route("/api/import-status")
def api_import_status() -> Any:
    """查询词库导入状态.

    Returns:
        JSON Response，含 importing 布尔字段。

    """
    return jsonify({"importing": _vocab_importing})


@app.route("/api/llm-status")
def api_llm_status() -> Any:
    """查询 LLM 端点连通状态.

    Returns:
        JSON Response，含 writer 和 checker 状态
       （"unknown" / "checking" / "ok" / "error"）。

    """
    return jsonify(dict(_llm_status))


@app.route("/api/llm-ping", methods=["POST"])
def api_llm_ping() -> Any:
    """手动触发 LLM 端点连通性探测.

    Returns:
        JSON Response，含 writer 和 checker 最新状态。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
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
    """返回指定语言的翻译 JSON.

    Args:
        lang: 语言代码（"zh" 或 "en"）。

    Returns:
        JSON Response，翻译字典。

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
    """主页面（注入 CSRF 令牌）.

    Returns:
        渲染后的 HTML 字符串。

    """
    return render_template("index.html", csrf_token=_CSRF_TOKEN)


@app.route("/api/templates")
def api_templates() -> Any:
    """模板列表接口.

    Returns:
        JSON Response，模板字典列表。

    """
    return jsonify(list_dicts())


@app.route("/api/templates/meta")
def api_templates_meta() -> Any:
    """自定义模板编辑器的逐语言约束元数据.

    Returns:
        JSON Response：{语言: {"attribute", "values", "helpers"}}。

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
    """保存用户自定义的模板显示顺序.

    Returns:
        JSON Response：成功时返回重排后的 key 顺序。

    Raises:
        400: 请求格式错误。
        403: CSRF 令牌校验失败。
        500: 顺序文件写入失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    raw_order = data.get("order")
    if not isinstance(raw_order, list) or not all(
        isinstance(key, str) for key in raw_order
    ):
        return jsonify({"status": "error", "message": "顺序必须是模板 key 列表"}), 400
    ordered = set_order(raw_order)
    try:
        _save_template_order(ordered)
    except OSError as e:
        return jsonify({"status": "error", "message": f"保存模板顺序失败: {e}"}), 500
    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("模板顺序已更新: %d 个模板", len(ordered))
    return jsonify({"status": "ok", "order": ordered})


@app.route("/api/templates/delete", methods=["POST"])
def api_delete_template() -> Any:
    """删除自定义模板（移除注册并删除落盘源码）.

    Returns:
        JSON Response：成功时返回删除的 key。

    Raises:
        400: 请求格式错误或尝试删除内置模板。
        403: CSRF 令牌校验失败。
        404: 模板不存在。
        500: 模板文件删除失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    key = str(data.get("key", "")).strip()
    if not key:
        return jsonify({"status": "error", "message": "请选择要删除的模板"}), 400
    registered_keys = [item["key"] for item in list_dicts()]
    if key not in registered_keys:
        return jsonify({"status": "error", "message": "模板不存在"}), 404
    if not key.startswith("custom_"):
        return jsonify({"status": "error", "message": "内置模板不能删除"}), 400
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
                {"status": "error", "message": f"模板文件删除失败: {e}"}
            ), 500
    unregister(key)
    sys.modules.pop(f"src.templates.{key}", None)
    try:
        _save_template_order([item["key"] for item in list_dicts()])
    except OSError as e:
        logger.warning("删除模板后保存顺序失败: %s", e)
    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("自定义模板已删除: %s", key)
    return jsonify({"status": "ok", "key": key, "count": len(list_dicts())})


def _template_source_code(base_key: str, template: Any) -> str:
    """返回源模板可供 AI 转写的代码文本.

    自定义模板优先读取落盘的源码文件；找不到时按模板规格重建等价源码。
    内置模板返回模板类源码，并附带同模块内定义的辅助函数/常量，便于 AI
    理解三平尾、孤平、步格等规则代码。

    Args:
        base_key: 源模板 key。
        template: 源模板对象（PoetryTemplate 实例）。

    Returns:
        源码文本；无法获取时返回空串。
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
        except Exception as e:  # noqa: BLE001 - 源码重建仅用于 AI 参考，失败返回空
            logger.warning("自定义模板源码重建失败 %s: %s", base_key, e)
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
    """统一的跨语言模板转化接口.

    读取源模板的完整规格（行数/每行音节/逐位约束/押韵韵式/自定义代码），
    只把逐位约束的属性值按映射转换为目标语言属性值，其余原样复制。
    前端“应用转换”与模板编辑 AI 的 set_from_template 工具共用此实现。

    Returns:
        JSON Response：成功时返回转化后的模板规格；失败返回错误信息。

    Raises:
        400: 请求格式错误、未知模板/语言或映射非法。
        403: CSRF 令牌校验失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    base_key = str(data.get("base_template_key", "")).strip()
    language = str(data.get("language", ""))
    if not base_key:
        return jsonify({"status": "error", "message": "请选择源模板"}), 400
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
                ai_error = "模板AI未配置，请先在设置中填写模板AI的 API Key"
            else:
                source_template = get_template(base_key)
                source_code = _template_source_code(base_key, source_template)
                if not source_code:
                    ai_error = "无法获取源模板代码，未进行 AI 转写"
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
                        ai_error = str(rewritten.get("message", "模板代码转写失败"))
        except Exception as e:  # noqa: BLE001 - AI 转写失败降级为确定性转化结果
            ai_error = f"模板代码 AI 转写失败: {e}"
        if ai_error:
            spec["ai_rewrite_error"] = ai_error
    return jsonify(spec)


@app.route("/api/config", methods=["GET"])
def api_get_config() -> Any:
    """读取 LLM 配置.

    Returns:
        JSON Response，含 writer 和 checker 端点配置。

    Raises:
        403: CSRF 令牌校验失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
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
    """保存 LLM 配置.

    Returns:
        JSON Response（成功或错误）。

    Raises:
        400: 请求格式错误。
        403: CSRF 令牌校验失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    from src.config import get_config

    config = get_config()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    for key in ("writer", "checker", "editor"):
        if key in data:
            value = data[key]
            if not isinstance(value, dict):
                return jsonify(
                    {"status": "error", "message": f"{key} 配置格式错误"}
                ), 400
            config.__setattr__(key, value)
    if "language" in data:
        lang = data["language"]
        if lang in ("zh", "en"):
            config.language = lang
    config.save()
    logger.info(
        "LLM 配置已保存 (writer.base_url=%s, checker.base_url=%s, editor.base_url=%s)",
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
    """Socket 连接建立.

    无返回值，无副作用。
    """


def _emit_done(session_id: str, result: Any) -> None:
    """向会话推送 done 事件.

    Args:
        session_id: SocketIO 会话 ID。
        result: 流水线结果状态。

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
    """开始生成：后台线程跑四步流水线.

    Args:
        data: 事件负载（topic 主题、template_key 模板键）。

    """
    from src.pipeline.pipeline import PoetryPipeline

    topic = str(data.get("topic", ""))
    template_key = str(data.get("template_key", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    if not topic or not template_key:
        emit("error", {"message": "主题和模板不能为空"})
        return

    logger.info(
        "generate 开始 session=%s template=%s topic=%r", session_id, template_key, topic
    )
    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """推送流水线进度到该会话.

        Args:
            state_dict: 流水线状态字典。

        """
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        """在后台线程执行四步流水线并推送 done/error 事件."""
        try:
            result = pipeline.run(
                topic=topic,
                template_key=template_key,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - 生成线程兜底：任何失败转为前端错误事件
            logger.error("generate 失败 session=%s: %s", session_id, e)
            socketio.emit("error", {"message": f"生成失败: {e}"}, to=session_id)
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "generate 完成 session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("feedback")
def handle_feedback(data: dict[str, Any]) -> None:
    """用户反馈续跑：打回 Step 3 按反馈重新炼句.

    Args:
        data: 事件负载（feedback 用户反馈文本）。

    """
    from src.pipeline.pipeline import PoetryPipeline

    feedback = str(data.get("feedback", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    session_data = _active_states.get(session_id, {})
    pipeline_state = session_data.get("pipeline_state")
    if pipeline_state is None:
        emit("error", {"message": "没有活跃的生成会话，请先生成诗歌"})
        return

    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """推送流水线进度到该会话.

        Args:
            state_dict: 流水线状态字典。

        """
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        """在后台线程按用户反馈续跑流水线并推送 done/error 事件."""
        try:
            result = pipeline.continue_with_feedback(
                state=pipeline_state,
                user_feedback=feedback,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - 反馈线程兜底：任何失败转为前端错误事件
            logger.error("feedback 失败 session=%s: %s", session_id, e)
            socketio.emit("error", {"message": f"反馈处理失败: {e}"}, to=session_id)
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "feedback 完成 session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


def _sequence_payload(state: Any) -> dict[str, Any]:
    """把诗组状态转为可推送/可序列化的字典.

    Args:
        state: SequenceState。

    Returns:
        前端可用的诗组字典。

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
    """开始诗组生成：规划 → 逐首生成/检查 → 汇总.

    Args:
        data: 事件负载（topic 诗组总目标；template_keys 每首格律 key 列表）。

    """
    from src.pipeline.sequence import PoemSequencePipeline

    topic = str(data.get("topic", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    if not topic:
        emit("error", {"message": "诗组主题不能为空"})
        return

    template_keys: list[str] | None = None
    if "template_keys" in data:
        raw = data.get("template_keys")
        if not isinstance(raw, list) or not raw:
            emit("error", {"message": "请至少为每首诗选择格律"})
            return
        template_keys = [str(item) for item in raw]

    logger.info("generate_sequence 开始 session=%s topic=%r", session_id, topic)
    pipeline = PoemSequencePipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        """推送诗组规划/生成进度到该会话.

        Args:
            state_dict: 诗组状态字典。

        """
        socketio.emit("sequence_progress", state_dict, to=session_id)

    def run() -> None:
        """在后台线程执行诗组流水线并推送 sequence_done/error 事件."""
        try:
            state = pipeline.run(
                topic, on_progress=on_progress, template_keys=template_keys
            )
        except Exception as e:  # noqa: BLE001 - 诗组线程兜底：任何失败转为前端错误事件
            logger.error("generate_sequence 失败 session=%s: %s", session_id, e)
            socketio.emit("error", {"message": f"诗组生成失败: {e}"}, to=session_id)
            return
        _active_sequences[session_id] = {"sequence_state": state}
        logger.info(
            "generate_sequence 完成 session=%s poems=%s ok=%s",
            session_id,
            len(state.poems),
            state.ok,
        )
        socketio.emit("sequence_done", _sequence_payload(state), to=session_id)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """连接断开：清理会话状态."""
    _active_states.pop(request.sid, None)  # type: ignore[attr-defined]  # flask_socketio 注入
    _active_sequences.pop(request.sid, None)  # type: ignore[attr-defined]  # flask_socketio 注入


def _render_constraint_table(constraints: list[Any]) -> str:
    """把一份逐位约束表渲染为 Python 字面量源码.

    Args:
        constraints: 逐位约束（行 -> 单元格 -> {attributes}）。

    Returns:
        Python 列表字面量源码。

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
    """生成自定义模板的 Python 源码（供 /api/templates/custom 落盘）.

    Args:
        name: 模板显示名。
        language: 语言代码（zh/en/fr/it/la）。
        lines: 行数。
        syllables_per_line: 每行音节数。
        dimension: 该语言的逐位约束属性键（"" 表示无语位约束）。
        constraints: 逐位约束（行 -> 单元格 -> {attributes}）。
        custom_code: 用户提供的 validate_full 附加代码。
        class_name: 生成的模板类名。
        file_key: 注册键（custom_<name>）。
        alternatives: 多份逐位约束表（满足任意一份即可）；为空时用 constraints。
        rhyme_scheme: 归一化韵式（如 "ABABCDCDEFEFGG"；空串表示不押韵）。
        rhyme_distinct: 不同韵组是否须互不相同。
        structural_rules: 已数据化的结构规则（如近体诗平仄骨架/三平尾/孤平）。
        rule_note: 用户填写的模板规则描述（会作为 prompt 提供给写作 AI）。

    Returns:
        可直接写入 src/templates/custom_*.py 的源码文本。

    """
    tables: list[Any] = (
        list(alternatives)
        if alternatives
        else ([list(constraints)] if constraints else [])
    )
    if not tables:
        tables = [[]]
    rendered_tables = [_render_constraint_table(list(table or [])) for table in tables]

    # 生成文件的 REUSE 头。SPDX 标记拆开拼接，避免本文件源码中出现被
    # REUSE 误解析为许可证表达式的连续字面量（reuse lint 会报 invalid）。
    spdx_line = "# SPDX-License-" + "Identifier: MIT"
    # 有数据化结构规则时，押韵与结构由 check_jinti_rules 统一校验，避免重复。
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
    """落盘并热注册一个自定义模板.

    Args:
        name: 模板显示名。
        language: 语言代码。
        lines: 行数。
        syllables_per_line: 每行音节数。
        alternatives: 多份逐位约束表。
        custom_code: 自定义整体校验代码。
        rhyme_scheme: 归一化韵式。
        rhyme_distinct: 不同韵组是否须互不相同。
        structural_rules: 已数据化的结构规则（可选）。
        rule_note: 用户填写的模板规则描述（可选，作为写作 AI 的 prompt）。

    Returns:
        (HTTP 状态码, 响应载荷)；成功载荷含模板 key。

    """
    import re

    safe_name = re.sub(r"\W+", "_", name).strip("_")
    if not safe_name:
        return 400, {
            "status": "error",
            "message": "模板名需包含字母或数字（当前名称无法生成合法标识符）",
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
        return 500, {"status": "error", "message": f"模板文件写入失败: {e}"}

    try:
        module = _load_custom_template_module(file_path)
        reg_func = getattr(module, f"register_custom_{safe_name}", None)
        if reg_func:
            reg_func()
    except Exception as e:  # noqa: BLE001 - 用户代码模板注册兜底：任何导入/执行错误回报 500
        return 500, {"status": "error", "message": f"注册失败: {e}"}

    socketio.emit("templates_updated", {"count": len(list_dicts())})
    logger.info("自定义模板已创建: %s (%s, %d 行)", name, language, lines)
    return 200, {
        "status": "ok",
        "message": f"模板'{name}'已创建并注册",
        "count": len(list_dicts()),
        "key": file_key,
    }


def _create_custom_template_from_draft(
    draft: Any,
) -> tuple[int, dict[str, Any]]:
    """把模板编辑 AI 的草稿落盘并注册.

    Args:
        draft: TemplateDraft 实例。

    Returns:
        (HTTP 状态码, 响应载荷)。

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
    """创建自定义格律模板（落盘为 src/templates/custom_*.py 并热注册）.

    Returns:
        JSON Response（成功含模板 key，或错误信息）。

    Raises:
        400: 请求格式错误或模板代码无效。
        403: CSRF 令牌校验失败。

    """
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
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
        return jsonify({"status": "error", "message": "模板名称不能为空"}), 400
    schemes = custom_template_schemes()
    if language not in schemes:
        return jsonify({"status": "error", "message": "不支持的语言"}), 400
    try:
        syllables_per_line = [max(1, int(s)) for s in syllables_per_line][:lines]
    except TypeError, ValueError:
        return jsonify({"status": "error", "message": "每行音节数格式错误"}), 400
    if len(syllables_per_line) != lines:
        return jsonify(
            {"status": "error", "message": "音节数列表长度必须等于行数"}
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
            {"status": "error", "message": "模板规则描述不能超过 4000 字"}
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
    """模板编辑 AI：后台线程配置模板并实时推送思考/回答/工具调用.

    Args:
        data: 事件负载（prompt 用户描述；draft 当前模板草稿）。

    """
    from src.agents.editor_ai import TemplateEditorAI
    from src.config import get_config

    prompt = str(data.get("prompt", "")).strip()
    raw_draft = data.get("draft")
    draft_payload = raw_draft if isinstance(raw_draft, dict) else {}
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    if not prompt:
        socketio.emit(
            "template_ai_done",
            {"status": "error", "message": "请先描述想要的模板"},
            to=session_id,
        )
        return

    editor_config = get_config().editor
    if not editor_config.get("api_key"):
        socketio.emit(
            "template_ai_done",
            {
                "status": "error",
                "message": "模板AI未配置，请先在设置中填写模板AI的 API Key",
            },
            to=session_id,
        )
        return

    logger.info("edit_template 开始 session=%s prompt=%r", session_id, prompt)

    def run() -> None:
        """在后台线程运行模板编辑 AI 并推送事件."""
        try:
            agent = TemplateEditorAI(editor_config)

            def on_event(event: dict[str, Any]) -> None:
                """推送一条模板AI事件到该会话.

                Args:
                    event: 事件字典。

                """
                socketio.emit("template_ai", event, to=session_id)

            result = agent.edit(prompt, draft_payload, emit=on_event)
        except Exception as e:  # noqa: BLE001 - 模板AI线程兜底：任何失败转为前端错误事件
            logger.error("edit_template 失败 session=%s: %s", session_id, e)
            socketio.emit(
                "template_ai_done",
                {"status": "error", "message": f"模板AI处理失败: {e}"},
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
            logger.info("模板AI已创建模板: %s", body.get("key"))
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
                    "message": str(body.get("message", "创建模板失败")),
                },
                to=session_id,
            )

    threading.Thread(target=run, daemon=True).start()


_HISTORY_DB_PATH: Path | None = None


def set_history_db_path(path: Path) -> None:
    """覆盖历史记录数据库路径（主要供测试使用）.

    Args:
        path: 新的数据库文件路径。

    """
    global _HISTORY_DB_PATH
    _HISTORY_DB_PATH = path


def get_history_db_path() -> Path:
    """返回历史记录数据库路径（默认 ~/.stanza_weaver/history.db）.

    Returns:
        数据库文件路径。

    """
    global _HISTORY_DB_PATH
    if _HISTORY_DB_PATH is None:
        _HISTORY_DB_PATH = Path.home() / ".stanza_weaver" / "history.db"
    return _HISTORY_DB_PATH


def _init_history_db() -> None:
    """初始化历史记录表（幂等）."""
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
    """读取历史记录（最近 50 条）.

    Returns:
        JSON Response，历史记录列表。

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
    """保存历史记录（定稿后由前端调用）.

    Returns:
        JSON Response（成功或错误）。

    Raises:
        400: 请求格式错误。
        403: CSRF 令牌校验失败。

    """
    import sqlite3

    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400

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
        "历史记录已保存: %s (%s)", data.get("template_name", ""), data.get("topic", "")
    )
    return jsonify({"status": "ok"})


def start_server() -> None:
    """启动 SocketIO 服务.

    监听地址/端口可用环境变量 STANZAWEAVER_HOST / STANZAWEAVER_PORT 覆盖
    （Docker 部署时设 STANZAWEAVER_HOST=0.0.0.0 配合端口映射）。
    """
    host = os.environ.get("STANZAWEAVER_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("STANZAWEAVER_PORT", "5000"))
    except ValueError:
        port = 5000
    logger.info("[StanzaWeaver] 服务启动 http://%s:%s", host, port)
    _start_background_threads()
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)


def main() -> None:
    """入口：优先 pywebview 桌面窗口，否则纯 HTTP 服务.

    桌面窗口初始化失败（如无显示环境/缺 GUI 库）时自动回退到 HTTP 服务，
    保证 Docker 等无头环境可用。

    Returns:
        None。

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
    except Exception as e:  # noqa: BLE001 - GUI 初始化失败兜底：回退 HTTP 服务
        logger.warning("GUI 初始化失败，回退到 HTTP 服务模式: %s", e)
        t.join()


if __name__ == "__main__":
    main()
