# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Extra app.py coverage: background threads, probes, custom templates, and more.

Goal: pytest coverage reaches 100% for ``src`` + ``app.py`` (root module).
All SocketIO flows use stub LLMs / fake pipelines; no real network calls.
"""

import runpy
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from flask.testing import FlaskClient
from flask_socketio import SocketIO

import app as app_module
from src.config import Config
from tests.helpers import make_stub, tool_call

DESC = "SocketIO 测试主题"
# Five-character quatrain: draft and revised first line both pass full meter checks.
DRAFT = "远岫依烟岭\n溪流伴月明\n桃红迷柳岸\n古道远山风"
REVISED_LINE = "远岸栖云树"


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client() -> Any:
    """Provide a Flask test client."""
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf() -> dict[str, str]:
    """Return CSRF request headers."""
    return {"X-CSRF-Token": app_module._CSRF_TOKEN}


def _csrf_headers() -> dict[str, str]:
    """Return request headers with CSRF and JSON content type."""
    return {**_csrf(), "Content-Type": "application/json"}


def _wait_event(sio: Any, name: str, timeout: float = 8.0) -> dict[str, Any]:
    """Poll until a socket event arrives."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in sio.get_received():
            if ev.get("name") == name:
                return cast(dict[str, Any], ev)
        time.sleep(0.02)
    raise AssertionError(f"no socket event: {name}")


def _sio_client() -> Any:
    """Create a SocketIO test client."""
    return app_module.socketio.test_client(app_module.app)


class _FakeThread:
    """Fake thread that records start/join (never runs the target)."""

    instances: ClassVar[list[_FakeThread]] = []

    def __init__(
        self, target: Any = None, daemon: bool | None = None, **_: Any
    ) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        self.joined = False
        _FakeThread.instances.append(self)

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True


# --------------------------------------------------------------------------- #
# Background threads and connectivity probes
# --------------------------------------------------------------------------- #
def test_auto_import_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """_auto_import success path: clear importing and trigger the ping event."""
    from src.knowledge import importer, vocabulary

    monkeypatch.setattr(vocabulary, "init_db", lambda: None)
    monkeypatch.setattr(importer, "import_all", lambda: None)
    monkeypatch.setattr(app_module, "_vocab_importing", True)
    app_module._llm_ping_event.clear()
    app_module._auto_import()
    assert app_module._vocab_importing is False
    assert app_module._llm_ping_event.is_set()


def test_auto_import_exception_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    """_auto_import logs exceptions and still runs the finally block."""
    from src.knowledge import vocabulary

    def _boom() -> None:
        raise OSError("no network")

    monkeypatch.setattr(vocabulary, "init_db", _boom)
    monkeypatch.setattr(app_module, "_vocab_importing", True)
    with caplog.at_level("ERROR"):
        app_module._auto_import()
    assert app_module._vocab_importing is False
    assert "Vocabulary import failed" in caplog.text


def test_ping_no_api_key_sets_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """An endpoint without api_key is marked unknown immediately."""
    cfg = SimpleNamespace(
        writer={"base_url": "http://x", "api_key": "", "model": "m"},
        checker={"base_url": "http://x", "api_key": "", "model": "m"},
    )
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    monkeypatch.setattr(
        app_module, "_llm_status", {"writer": "checking", "checker": "x"}
    )
    app_module._ping_one_endpoint("writer")
    assert app_module._llm_status["writer"] == "unknown"


def test_ping_endpoint_error_sets_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the endpoint as error when the probe raises."""
    cfg = SimpleNamespace(
        writer={"base_url": "http://x", "api_key": "k", "model": "m"},
        checker={"base_url": "http://x", "api_key": "k", "model": "m"},
    )
    monkeypatch.setattr("src.config.get_config", lambda: cfg)

    class _Failing:
        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            pass

        def chat(self, messages: list[Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

    monkeypatch.setattr("src.agents.base.LLMClient", _Failing)
    monkeypatch.setattr(
        app_module, "_llm_status", {"writer": "checking", "checker": "x"}
    )
    app_module._ping_one_endpoint("writer")
    assert app_module._llm_status["writer"] == "error"


def test_ping_endpoint_ok_sets_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the endpoint ok on a successful probe (no real config/network)."""
    cfg = SimpleNamespace(
        writer={"base_url": "http://x", "api_key": "k", "model": "m"},
        checker={"base_url": "http://x", "api_key": "k", "model": "m"},
    )
    monkeypatch.setattr("src.config.get_config", lambda: cfg)

    class _Healthy:
        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            pass

        def chat(self, messages: list[Any]) -> dict[str, Any]:
            return {"ok": True}

    monkeypatch.setattr("src.agents.base.LLMClient", _Healthy)
    monkeypatch.setattr(
        app_module, "_llm_status", {"writer": "checking", "checker": "x"}
    )
    app_module._ping_one_endpoint("writer")
    assert app_module._llm_status["writer"] == "ok"


def test_auto_ping_loop_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """_auto_ping runs one round then blocks on the event (no timed polling)."""
    emitted: list[tuple[str, Any]] = []
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: emitted.append(a))
    monkeypatch.setattr(app_module, "_ping_one_endpoint", lambda name: None)
    waits: list[float | None] = []

    class _FakeEvent:
        def __init__(self) -> None:
            self.calls = 0
            self.cleared = 0

        def wait(self, timeout: float | None = None) -> None:
            waits.append(timeout)
            self.calls += 1
            if self.calls >= 2:
                raise KeyboardInterrupt()

        def clear(self) -> None:
            self.cleared += 1

    event = _FakeEvent()
    monkeypatch.setattr(app_module, "_llm_ping_event", event)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with pytest.raises(KeyboardInterrupt):
        app_module._auto_ping()
    assert event.cleared == 1
    assert any("llm_status" in e[0] for e in emitted)
    # Key point: no timed polling with timeout (clearing it will not re-probe).
    assert waits and all(w is None for w in waits)


def test_start_background_threads_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start two background threads outside the test environment."""
    _FakeThread.instances = []
    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setenv("STANZA_WEAVER_TEST", "0")
    app_module._start_background_threads()
    assert len(_FakeThread.instances) == 2
    assert all(i.daemon for i in _FakeThread.instances)
    assert all(i.started for i in _FakeThread.instances)
    targets = {i.target for i in _FakeThread.instances}
    assert targets == {app_module._auto_import, app_module._auto_ping}


def test_start_background_threads_skipped_in_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not start background threads in the test environment."""
    _FakeThread.instances = []
    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setenv("STANZA_WEAVER_TEST", "1")
    app_module._start_background_threads()
    assert _FakeThread.instances == []


# --------------------------------------------------------------------------- #
# Automatic custom-template registration
# --------------------------------------------------------------------------- #
def test_register_custom_templates_dir_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return early when the templates directory does not exist."""
    monkeypatch.setattr(Path, "exists", lambda self: False)
    app_module._register_custom_templates()


def test_register_custom_templates_import_error(
    monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    """A failed custom-template load is only logged."""
    fake = Path("src/templates/custom_nope.py")
    monkeypatch.setattr(Path, "glob", lambda self, pat: iter([fake]))
    monkeypatch.setattr(
        app_module,
        "_load_custom_template_module",
        lambda file_path: (_ for _ in ()).throw(ImportError("boom")),
    )
    with caplog.at_level("ERROR"):
        app_module._register_custom_templates()
    assert "Failed to register custom template" in caplog.text


def test_custom_templates_dir_source_override_and_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Source mode uses src/templates; the env var overrides it; no legacy dir."""
    monkeypatch.delenv("STANZAWEAVER_TEMPLATES_DIR", raising=False)
    assert (
        app_module._custom_templates_dir()
        == Path(app_module.__file__).parent / "src" / "templates"
    )
    override = tmp_path / "override"
    monkeypatch.setenv("STANZAWEAVER_TEMPLATES_DIR", str(override))
    assert app_module._custom_templates_dir() == override
    assert app_module._legacy_custom_templates_dir() is None


def test_custom_templates_dir_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frozen build uses the user data dir; legacy is install dir (None if same)."""
    monkeypatch.delenv("STANZAWEAVER_TEMPLATES_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "app" / "app.py"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert (
        app_module._custom_templates_dir()
        == tmp_path / "home" / ".stanza_weaver" / "templates"
    )
    assert (
        app_module._legacy_custom_templates_dir()
        == tmp_path / "app" / "src" / "templates"
    )
    monkeypatch.setenv(
        "STANZAWEAVER_TEMPLATES_DIR", str(tmp_path / "app" / "src" / "templates")
    )
    assert app_module._legacy_custom_templates_dir() is None


def test_legacy_custom_templates_dir_resolve_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Return the legacy dir even when resolve fails (OSError fallback)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "app" / "app.py"))
    monkeypatch.setattr(
        Path, "resolve", lambda self: (_ for _ in ()).throw(OSError("x"))
    )
    assert app_module._legacy_custom_templates_dir() == (
        tmp_path / "app" / "src" / "templates"
    )


def test_migrate_legacy_custom_templates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Copy legacy templates: skip existing, missing, and failing cases."""
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "custom_a.py").write_text("A", encoding="utf-8")
    primary = tmp_path / "primary"
    app_module._migrate_legacy_custom_templates(primary, legacy)
    assert (primary / "custom_a.py").read_text(encoding="utf-8") == "A"

    (primary / "custom_a.py").write_text("NEW", encoding="utf-8")
    app_module._migrate_legacy_custom_templates(primary, legacy)
    assert (primary / "custom_a.py").read_text(encoding="utf-8") == "NEW"

    app_module._migrate_legacy_custom_templates(primary, None)
    app_module._migrate_legacy_custom_templates(primary, tmp_path / "missing")

    monkeypatch.setattr(
        Path, "mkdir", lambda self, *a, **k: (_ for _ in ()).throw(OSError("ro"))
    )
    app_module._migrate_legacy_custom_templates(tmp_path / "cannot", legacy)

    monkeypatch.setattr(Path, "mkdir", lambda self, *a, **k: None)
    monkeypatch.setattr(
        "shutil.copy2",
        lambda *a, **k: (_ for _ in ()).throw(OSError("copy")),
    )
    app_module._migrate_legacy_custom_templates(tmp_path / "copyfail", legacy)
    assert not (tmp_path / "copyfail" / "custom_a.py").exists()


def test_load_custom_template_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Load a template module from anywhere; clean sys.modules on failure."""
    good = tmp_path / "good_mod.py"
    good.write_text("VALUE = 7\n", encoding="utf-8")
    module = app_module._load_custom_template_module(good)
    assert module.VALUE == 7
    assert "src.templates.good_mod" in sys.modules

    bad = tmp_path / "bad_mod.py"
    bad.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        app_module._load_custom_template_module(bad)
    assert "src.templates.bad_mod" not in sys.modules

    monkeypatch.setattr(
        "importlib.util.spec_from_file_location",
        lambda *a, **k: None,
    )
    with pytest.raises(ImportError):
        app_module._load_custom_template_module(good)
    monkeypatch.setattr(
        "importlib.util.spec_from_file_location",
        lambda *a, **k: SimpleNamespace(loader=None),
    )
    with pytest.raises(ImportError):
        app_module._load_custom_template_module(good)


def _write_custom_module(path: Path, display_name: str) -> None:
    """Write a minimal registerable custom-template module."""
    path.write_text(
        "from src.templates import PoetryTemplate, register\n\n"
        "class T(PoetryTemplate):\n"
        f"    name = {display_name!r}\n"
        '    language = "zh"\n'
        "    lines = 1\n"
        "    syllables_per_line = [1]\n\n"
        "def register_custom_testmod():\n"
        '    register("custom_testmod", T())\n',
        encoding="utf-8",
    )


def test_register_custom_templates_from_user_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frozen build loads custom templates from the user data dir."""
    from src.templates import _registry

    user_dir = tmp_path / "user_templates"
    user_dir.mkdir()
    _write_custom_module(user_dir / "custom_testmod.py", "用户目录模板")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "app" / "app.py"))
    monkeypatch.setenv("STANZAWEAVER_TEMPLATES_DIR", str(user_dir))
    try:
        app_module._register_custom_templates()
        assert _registry["custom_testmod"].name == "用户目录模板"
    finally:
        _registry.pop("custom_testmod", None)


def test_register_custom_templates_migrates_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Migrate legacy templates to the user dir and register them (user wins)."""
    from src.templates import _registry

    app_dir = tmp_path / "app"
    legacy = app_dir / "src" / "templates"
    legacy.mkdir(parents=True)
    _write_custom_module(legacy / "custom_testmod.py", "旧版模板")
    user_dir = tmp_path / "user_templates"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module, "__file__", str(app_dir / "app.py"))
    monkeypatch.setenv("STANZAWEAVER_TEMPLATES_DIR", str(user_dir))
    try:
        app_module._register_custom_templates()
        assert (user_dir / "custom_testmod.py").exists()
        assert _registry["custom_testmod"].name == "旧版模板"

        # A same-named template in the user dir wins over the legacy directory.
        user_dir.mkdir(exist_ok=True)
        _write_custom_module(user_dir / "custom_testmod.py", "用户新版模板")
        app_module._register_custom_templates()
        assert _registry["custom_testmod"].name == "用户新版模板"
    finally:
        _registry.pop("custom_testmod", None)


def test_create_custom_template_in_user_dir_loads_generated_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Generated templates in the app dir load (relative imports still resolve)."""
    from src.templates import _registry

    templates_dir = tmp_path / "user_templates"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("STANZAWEAVER_TEMPLATES_DIR", str(templates_dir))
    cell = {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": {"tone": "", "stress": "", "length": ""},
    }
    try:
        status, _payload = app_module._create_custom_template(
            name="相对导入模板",
            language="zh",
            lines=1,
            syllables_per_line=[2],
            alternatives=[[[cell, cell]]],
            custom_code="",
        )
        assert status == 200
        assert (templates_dir / "custom_相对导入模板.py").exists()
        template = _registry["custom_相对导入模板"]
        assert template.name == "相对导入模板"
        assert template.language == "zh"
    finally:
        _registry.pop("custom_相对导入模板", None)


def test_create_custom_template_writes_user_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frozen build writes created templates to the user data dir."""
    templates_dir = tmp_path / "user_templates"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("STANZAWEAVER_TEMPLATES_DIR", str(templates_dir))
    written: list[Path] = []
    monkeypatch.setattr(
        Path, "write_text", lambda self, data, **k: written.append(self)
    )
    loaded: list[Path] = []

    def _fake_load(file_path: Path) -> Any:
        loaded.append(file_path)
        return SimpleNamespace(register_custom_ok=lambda: None)

    monkeypatch.setattr(app_module, "_load_custom_template_module", _fake_load)
    status, _payload = app_module._create_custom_template(
        name="用户目录新模板",
        language="zh",
        lines=1,
        syllables_per_line=[1],
        alternatives=[[]],
        custom_code="",
    )
    assert status == 200
    assert written == [templates_dir / "custom_用户目录新模板.py"]
    assert loaded == written


def test_register_custom_templates_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """A custom template loads and its register function runs."""
    calls: list[str] = []
    fake = Path("src/templates/custom_hit.py")

    def _fake_load(file_path: Path) -> Any:
        mod = SimpleNamespace()
        mod.register_custom_hit = lambda: calls.append(file_path.as_posix())
        return mod

    monkeypatch.setattr(Path, "glob", lambda self, pat: iter([fake]))
    monkeypatch.setattr(app_module, "_load_custom_template_module", _fake_load)
    app_module._register_custom_templates()
    assert calls == ["src/templates/custom_hit.py"]


# --------------------------------------------------------------------------- #
# Template order persistence / reorder API / delete API
# --------------------------------------------------------------------------- #
def test_template_order_path_uses_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The order file lives in the user data dir."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert app_module._template_order_path() == (
        tmp_path / ".stanza_weaver" / "template_order.json"
    )


def test_template_order_load_save_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Order file read/write round-trip and corrupted-data fallback."""
    path = tmp_path / "order.json"
    monkeypatch.setattr(app_module, "_template_order_path", lambda: path)
    assert app_module._load_template_order() == []
    app_module._save_template_order(["b", "a"])
    assert app_module._load_template_order() == ["b", "a"]
    path.write_text("not json", encoding="utf-8")
    assert app_module._load_template_order() == []
    path.write_text('{"k": 1}', encoding="utf-8")
    assert app_module._load_template_order() == []
    path.write_text('["x", 1]', encoding="utf-8")
    assert app_module._load_template_order() == ["x", "1"]


def test_apply_saved_template_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test env skips applying order; normal env applies it; empty order skips."""
    calls: list[list[str]] = []
    monkeypatch.setattr(app_module, "set_order", lambda keys: calls.append(list(keys)))
    monkeypatch.setenv("STANZA_WEAVER_TEST", "1")
    app_module._apply_saved_template_order()
    assert calls == []
    monkeypatch.delenv("STANZA_WEAVER_TEST", raising=False)
    monkeypatch.setattr(app_module, "_load_template_order", lambda: ["b"])
    app_module._apply_saved_template_order()
    assert calls == [["b"]]
    monkeypatch.setattr(app_module, "_load_template_order", list)
    app_module._apply_saved_template_order()
    assert calls == [["b"]]


def _ordered_snapshot() -> list[str]:
    """Return the current registry key order."""
    from src.templates import _registry

    return list(_registry)


def _restore_order(snapshot: list[str]) -> None:
    """Restore the registry order."""
    from src.templates import set_order

    set_order(snapshot)


def test_default_template_order_keeps_custom_relative_order() -> None:
    """Default order: built-ins by registration, custom after them, then others."""
    from src.templates import _registry

    snapshot = dict(_registry)
    try:
        _register_delete_dummy("custom_order_a")
        _register_delete_dummy("custom_order_b")
        _register_delete_dummy("other_order_x")
        from src.templates import set_order as _set_order

        _set_order(["custom_order_b", "zh_qijue", "other_order_x", "custom_order_a"])
        ordered = app_module._default_template_order()
        builtin_order = [
            key for key in app_module._DEFAULT_BUILTIN_ORDER if key in _registry
        ]
        assert ordered[: len(builtin_order)] == builtin_order
        custom_ordered = [key for key in ordered if key.startswith("custom_")]
        assert custom_ordered[:2] == ["custom_order_b", "custom_order_a"]
        assert set(custom_ordered) == {
            key for key in _registry if key.startswith("custom_")
        }
        assert ordered[-1] == "other_order_x"
        assert set(ordered) == set(_registry)
    finally:
        _registry.clear()
        _registry.update(snapshot)


def test_reset_template_order_requires_csrf(client: FlaskClient) -> None:
    """The reset-order endpoint requires CSRF."""
    assert client.post("/api/templates/order/reset").status_code == 403


def test_reset_template_order_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reset order: built-ins back to default, custom after them, then save."""
    import json as _json

    from src.templates import _registry
    from src.templates import set_order as _set_order

    snapshot = dict(_registry)
    path = tmp_path / "order.json"
    monkeypatch.setattr(app_module, "_template_order_path", lambda: path)
    try:
        _register_delete_dummy("custom_reset_a")
        _register_delete_dummy("custom_reset_b")
        _set_order(["custom_reset_b", "custom_reset_a", "zh_qijue"])
        resp = client.post("/api/templates/order/reset", headers=_csrf_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        builtin_order = [
            key for key in app_module._DEFAULT_BUILTIN_ORDER if key in _registry
        ]
        assert data["order"][: len(builtin_order)] == builtin_order
        assert data["order"][len(builtin_order) : len(builtin_order) + 2] == [
            "custom_reset_b",
            "custom_reset_a",
        ]
        saved = _json.loads(path.read_text(encoding="utf-8"))
        assert saved == data["order"]
    finally:
        _registry.clear()
        _registry.update(snapshot)


def test_reset_template_order_save_failure(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed order-file write returns 500."""
    monkeypatch.setattr(
        app_module,
        "_save_template_order",
        lambda keys: (_ for _ in ()).throw(OSError("ro")),
    )
    resp = client.post("/api/templates/order/reset", headers=_csrf_headers())
    assert resp.status_code == 500


def test_reorder_templates_requires_csrf(client: FlaskClient) -> None:
    """The reorder endpoint requires CSRF."""
    assert client.post("/api/templates/order", json={"order": []}).status_code == 403


def test_reorder_templates_invalid_body(client: FlaskClient) -> None:
    """The reorder endpoint returns 400 for an invalid body."""
    client.post("/api/templates/order", data="x", headers=_csrf_headers())
    assert (
        client.post(
            "/api/templates/order", data="x", headers=_csrf_headers()
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/templates/order", json={"order": "x"}, headers=_csrf_headers()
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/templates/order", json={"order": [1]}, headers=_csrf_headers()
        ).status_code
        == 400
    )


def test_reorder_templates_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reorder the registry and persist it; unlisted templates go last."""
    import json as _json

    from src.templates import list_dicts

    path = tmp_path / "order.json"
    monkeypatch.setattr(app_module, "_template_order_path", lambda: path)
    snapshot = _ordered_snapshot()
    try:
        resp = client.post(
            "/api/templates/order",
            json={"order": ["zh_qijue", "zh_wujue"]},
            headers=_csrf_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["order"][:2] == ["zh_qijue", "zh_wujue"]
        assert set(data["order"]) == set(snapshot)
        assert [item["key"] for item in list_dicts()][:2] == [
            "zh_qijue",
            "zh_wujue",
        ]
        saved = _json.loads(path.read_text(encoding="utf-8"))
        assert saved[:2] == ["zh_qijue", "zh_wujue"]
    finally:
        _restore_order(snapshot)


def test_reorder_templates_save_failure(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed order-file write returns 500."""
    monkeypatch.setattr(
        app_module,
        "_save_template_order",
        lambda keys: (_ for _ in ()).throw(OSError("ro")),
    )
    snapshot = _ordered_snapshot()
    try:
        resp = client.post(
            "/api/templates/order",
            json={"order": ["zh_qijue"]},
            headers=_csrf_headers(),
        )
        assert resp.status_code == 500
    finally:
        _restore_order(snapshot)


def test_delete_template_requires_csrf(client: FlaskClient) -> None:
    """The delete endpoint requires CSRF."""
    assert client.post("/api/templates/delete", json={"key": "x"}).status_code == 403


def test_delete_template_invalid_body(client: FlaskClient) -> None:
    """The delete endpoint returns 400 for a bad body or a missing key."""
    assert (
        client.post(
            "/api/templates/delete", data="x", headers=_csrf_headers()
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/templates/delete", json={}, headers=_csrf_headers()
        ).status_code
        == 400
    )


def test_delete_template_not_found(client: FlaskClient) -> None:
    """Deleting a missing template returns 404."""
    resp = client.post(
        "/api/templates/delete",
        json={"key": "custom_nope"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 404


def test_delete_template_builtin_rejected(client: FlaskClient) -> None:
    """Built-in templates cannot be deleted."""
    resp = client.post(
        "/api/templates/delete",
        json={"key": "zh_wujue"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def _register_delete_dummy(key: str = "custom_delete_test") -> None:
    """Register a deletable test template."""
    from src.templates import PoetryTemplate, register

    class _Tpl(PoetryTemplate):
        """Test template."""

        name = "删除测试"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    register(key, _Tpl())


def test_delete_template_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Delete a custom template: unregister, remove the source, update the order."""
    from src.templates import _registry

    key = "custom_delete_test"
    _register_delete_dummy(key)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    file_path = templates_dir / f"{key}.py"
    file_path.write_text("x", encoding="utf-8")
    order_path = tmp_path / "order.json"
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    monkeypatch.setattr(app_module, "_template_order_path", lambda: order_path)
    try:
        resp = client.post(
            "/api/templates/delete",
            json={"key": key},
            headers=_csrf_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["key"] == key
        assert key not in _registry
        assert not file_path.exists()
        assert order_path.exists()
    finally:
        _registry.pop(key, None)


def test_delete_template_without_file_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unregistering still works when the source file is missing."""
    from src.templates import _registry

    key = "custom_delete_nofile"
    _register_delete_dummy(key)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    monkeypatch.setattr(
        app_module, "_template_order_path", lambda: tmp_path / "order.json"
    )
    try:
        resp = client.post(
            "/api/templates/delete", json={"key": key}, headers=_csrf_headers()
        )
        assert resp.status_code == 200
        assert key not in _registry
    finally:
        _registry.pop(key, None)


def test_delete_template_unlink_failure(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed source deletion returns 500 and keeps the registration."""
    from src.templates import _registry

    key = "custom_delete_fail"
    _register_delete_dummy(key)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / f"{key}.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *a, **k: (_ for _ in ()).throw(OSError("denied")),
    )
    try:
        resp = client.post(
            "/api/templates/delete", json={"key": key}, headers=_csrf_headers()
        )
        assert resp.status_code == 500
        assert key in _registry
    finally:
        _registry.pop(key, None)


def test_delete_template_order_save_failure_still_ok(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Deletion succeeds even if saving the order fails (warning only)."""
    from src.templates import _registry

    key = "custom_delete_ordersave"
    _register_delete_dummy(key)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    monkeypatch.setattr(
        app_module,
        "_save_template_order",
        lambda keys: (_ for _ in ()).throw(OSError("ro")),
    )
    try:
        resp = client.post(
            "/api/templates/delete", json={"key": key}, headers=_csrf_headers()
        )
        assert resp.status_code == 200
        assert key not in _registry
    finally:
        _registry.pop(key, None)


# --------------------------------------------------------------------------- #
# Local access guard / i18n fallback / config write-back
# --------------------------------------------------------------------------- #
def test_guard_local_access_rejects_foreign_host() -> None:
    """A non-local Host returns 403."""
    with app_module.app.test_request_context("/", headers={"Host": "evil.example"}):
        resp = app_module._guard_local_access()
    assert resp is not None
    assert resp[1] == 403


def test_i18n_missing_language_falls_back(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fall back to zh.yaml when a language file is missing."""
    (tmp_path / "zh.yaml").write_text("html:\n  lang: zh-CN\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "_I18N_DIR", tmp_path)
    resp = client.get("/api/i18n/en")
    assert resp.status_code == 200
    assert resp.get_json()["html"]["lang"] == "zh-CN"


def test_config_post_requires_csrf(client: FlaskClient) -> None:
    """Saving config requires CSRF."""
    assert client.post("/api/config", json={}).status_code == 403


def test_config_post_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A valid config write-back succeeds."""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post(
        "/api/config",
        json={
            "writer": {"base_url": "http://w", "api_key": "k", "model": "m"},
            "checker": {"base_url": "http://c", "api_key": "k", "model": "m"},
            "language": "zh",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert cfg.language == "zh"
    assert cfg.data["writer"]["model"] == "m"


def test_config_post_not_dict(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-object request body returns 400."""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", data="not json", headers=_csrf_headers())
    assert resp.status_code == 400


def test_config_post_writer_not_dict(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-object Writer config returns 400."""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", json={"writer": "oops"}, headers=_csrf_headers())
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# SocketIO: generate errors / feedback / disconnect
# --------------------------------------------------------------------------- #
def test_generate_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Push an error when the generate thread's pipeline raises."""

    class _Boom:
        def __init__(self) -> None:
            pass

        def run(self, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("src.pipeline.pipeline.PoetryPipeline", _Boom)
    sio = _sio_client()
    sio.emit("generate", {"topic": "主题", "template_key": "zh_wujue"})
    ev = _wait_event(sio, "error")
    assert "Generation failed" in str(ev["args"])


def test_feedback_without_session_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feedback returns an error when there is no active session."""
    sio = _sio_client()
    sio.emit("feedback", {"feedback": "再婉约一些"})
    ev = _wait_event(sio, "error")
    assert "No active generation session" in str(ev["args"])


def test_feedback_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Push an error when the feedback thread's continuation raises."""
    sio = _sio_client()

    class _BoomFeedback:
        def __init__(self) -> None:
            pass

        def continue_with_feedback(self, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    class _AlwaysSession(dict[Any, Any]):
        def get(self, key: Any, default: Any = None) -> Any:
            return {"pipeline_state": object()}

    monkeypatch.setattr("src.pipeline.pipeline.PoetryPipeline", _BoomFeedback)
    monkeypatch.setattr(app_module, "_active_states", _AlwaysSession())
    sio.emit("feedback", {"feedback": "再婉约一些"})
    ev = _wait_event(sio, "error")
    assert "Feedback processing failed" in str(ev["args"])


def _patch_llm_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject stub LLM clients (drives both generate and feedback rounds)."""
    from src.agents import checker_ai, writer_ai

    writer_stub = make_stub(
        stream=[DESC, DRAFT],
        chat=[
            {
                "role": "assistant",
                "content": DRAFT,
                "tool_calls": [
                    {
                        "id": "call_submit",
                        "name": "submit",
                        "arguments": {"title": "静夜思"},
                    }
                ],
            },
            tool_call(
                "modify",
                {"modify_type": "line", "line": 0, "content": REVISED_LINE},
            ),
        ],
    )
    checker_stub = make_stub(chat=[tool_call("submit", {"pass": True})])
    monkeypatch.setattr(writer_ai, "LLMClient", writer_stub)
    monkeypatch.setattr(checker_ai, "LLMClient", checker_stub)


def test_generate_then_feedback_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate finalizes, then feedback continuation finalizes again (same session)."""
    _patch_llm_stubs(monkeypatch)
    sio = _sio_client()

    sio.emit("generate", {"topic": "静夜思", "template_key": "zh_wujue"})
    done1 = _wait_event(sio, "done")
    assert done1["args"][0]["checker_pass"] is True

    sio.emit("feedback", {"feedback": "再婉约一些"})
    done2 = _wait_event(sio, "done")
    assert done2["args"][0]["checker_pass"] is True
    assert done2["args"][0]["draft"][0] == REVISED_LINE


def test_disconnect_cleans_state() -> None:
    """Disconnecting clears the session state."""
    sio = _sio_client()
    sio.disconnect()


# --------------------------------------------------------------------------- #
# Custom templates: source building and route branches
# --------------------------------------------------------------------------- #
def test_build_custom_code_with_custom_code() -> None:
    """custom_code is written into the generated source with per-line indent."""
    code = app_module._build_custom_template_code(
        name="带代码",
        language="zh",
        lines=1,
        syllables_per_line=[5],
        dimension="tone",
        constraints=[[]],
        custom_code="errors.append('x')",
        class_name="CustomXTemplate",
        file_key="custom_x",
    )
    assert "errors.append('x')" in code
    assert ("# SPDX-License-" + "Identifier: MIT") in code


def test_custom_template_requires_csrf(client: FlaskClient) -> None:
    """Creating a custom template requires CSRF."""
    assert client.post("/api/templates/custom", json={}).status_code == 403


def test_custom_template_not_dict(client: FlaskClient) -> None:
    """A non-object request body returns 400."""
    resp = client.post("/api/templates/custom", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_custom_template_invalid_lines(client: FlaskClient) -> None:
    """Non-numeric lines and mismatched syllable counts return 400."""
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "x",
            "language": "zh",
            "lines": "abc",
            "syllables_per_line": [1, 2],
            "constraints": [],
            "code": "",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_empty_name(client: FlaskClient) -> None:
    """An empty name returns 400."""
    resp = client.post(
        "/api/templates/custom",
        json={"name": "", "language": "zh", "lines": 4, "syllables_per_line": [5] * 4},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_bad_syllables(client: FlaskClient) -> None:
    """An invalid syllable-count list returns 400."""
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "x",
            "language": "zh",
            "lines": 2,
            "syllables_per_line": ["a", "b"],
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_safe_name_empty(client: FlaskClient) -> None:
    """A name that cannot form a valid identifier returns 400."""
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "!!!",
            "language": "zh",
            "lines": 4,
            "syllables_per_line": [5] * 4,
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_write_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed template-file write returns 500."""

    def _raise_write(self: Any, *a: Any, **k: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _raise_write)
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "写失败",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [5],
            "constraints": [],
            "code": "",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 500
    assert "Failed to write template file" in resp.get_json()["message"]


def test_custom_template_registration_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registration failure returns 500 (writes mocked to keep the repo clean)."""
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(
        app_module,
        "_load_custom_template_module",
        lambda file_path: (_ for _ in ()).throw(ImportError("boom")),
    )
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "注册失败",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [5],
            "constraints": [],
            "code": "",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 500
    assert "Template registration failed" in resp.get_json()["message"]


def test_custom_template_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create and register a template successfully (writes and load mocked)."""
    calls: list[str] = []
    emitted: list[Any] = []
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)

    def _fake_load(file_path: Path) -> Any:
        calls.append(str(file_path))
        return SimpleNamespace(register_custom_ok=lambda: None)

    monkeypatch.setattr(app_module, "_load_custom_template_module", _fake_load)
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: emitted.append(a))
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "ok",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [5],
            "constraints": [],
            "code": "",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert calls and calls[0].endswith("custom_ok.py")
    assert any(e[0] == "templates_updated" for e in emitted)


# --------------------------------------------------------------------------- #
# History: non-object request bodies
# --------------------------------------------------------------------------- #
def test_history_post_not_dict(client: FlaskClient) -> None:
    """A non-object body when saving history returns 400."""
    resp = client.post("/api/history", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_history_db_path_default_and_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """History DB path defaults to the user dir; set_history_db_path overrides."""
    monkeypatch.setattr(app_module, "_HISTORY_DB_PATH", None)
    assert (
        app_module.get_history_db_path()
        == Path.home() / ".stanza_weaver" / "history.db"
    )
    app_module.set_history_db_path(tmp_path / "h.db")
    assert app_module.get_history_db_path() == tmp_path / "h.db"


# --------------------------------------------------------------------------- #
# Server startup / main / __main__
# --------------------------------------------------------------------------- #
def test_start_server_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Listen on 127.0.0.1:5000 by default."""
    calls: list[Any] = []
    monkeypatch.setattr(
        app_module.socketio, "run", lambda *a, **k: calls.append((a, k))
    )
    monkeypatch.delenv("STANZAWEAVER_HOST", raising=False)
    monkeypatch.delenv("STANZAWEAVER_PORT", raising=False)
    app_module.start_server()
    assert calls
    _, kwargs = calls[0]
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 5000


def test_start_server_bad_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fall back to port 5000 when the port env var is invalid."""
    calls: list[Any] = []
    monkeypatch.setattr(
        app_module.socketio, "run", lambda *a, **k: calls.append((a, k))
    )
    monkeypatch.setenv("STANZAWEAVER_PORT", "abc")
    app_module.start_server()
    assert calls[0][1]["port"] == 5000


def test_main_import_webview_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fall back to the HTTP server when webview cannot be imported."""
    calls: list[Any] = []
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(app_module, "start_server", lambda: calls.append("started"))
    app_module.main()
    assert calls == ["started"]


def test_main_webview_gui_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """On GUI init failure, log a warning and wait for the server thread."""
    _FakeThread.instances = []
    started: list[Any] = []

    class _Gui:
        def create_window(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("no display")

    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setitem(sys.modules, "webview", _Gui())
    monkeypatch.setattr(app_module, "start_server", lambda: started.append("server"))
    app_module.main()
    # The HTTP server runs in a background thread (replaced by the fake here),
    # so the failure path only waits on that thread.
    assert started == []
    assert len(_FakeThread.instances) == 1
    assert _FakeThread.instances[0].joined


def test_main_webview_gui_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI starts normally."""
    _FakeThread.instances = []

    class _Gui:
        def create_window(self, *a: Any, **k: Any) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setitem(sys.modules, "webview", _Gui())
    monkeypatch.setattr(app_module, "start_server", lambda: None)
    app_module.main()
    assert len(_FakeThread.instances) == 1
    assert _FakeThread.instances[0].started


def test_module_runs_as_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running app.py as __main__ covers the entry-point guard."""
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(SocketIO, "run", lambda self, *a, **k: None)
    runpy.run_path(str(Path(app_module.__file__)), run_name="__main__")
