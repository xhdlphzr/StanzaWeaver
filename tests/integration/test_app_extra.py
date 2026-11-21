# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""app.py 补齐覆盖：后台线程/连通性探测/自定义模板落盘/配置写回/反馈续跑等.

目标：pytest 覆盖率覆盖 ``src`` + ``app.py``（根目录模块）达到 100%。
所有 SocketIO 流程使用桩 LLM / 假 Pipeline，绝不发起真实网络请求。
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
# 五言绝句（合律）：初稿与修改后首行均通过全量格律校验。
DRAFT = "远岫依烟岭\n溪流伴月明\n桃红迷柳岸\n古道远山风"
REVISED_LINE = "远岸栖云树"


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client() -> Any:
    """提供 Flask 测试客户端."""
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf() -> dict[str, str]:
    """返回 CSRF 请求头."""
    return {"X-CSRF-Token": app_module._CSRF_TOKEN}


def _csrf_headers() -> dict[str, str]:
    """返回含 CSRF 与 JSON 类型的请求头."""
    return {**_csrf(), "Content-Type": "application/json"}


def _wait_event(sio: Any, name: str, timeout: float = 8.0) -> dict[str, Any]:
    """轮询等待某个 socket 事件."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in sio.get_received():
            if ev.get("name") == name:
                return cast(dict[str, Any], ev)
        time.sleep(0.02)
    raise AssertionError(f"no socket event: {name}")


def _sio_client() -> Any:
    """创建 socketio 测试客户端."""
    return app_module.socketio.test_client(app_module.app)


class _FakeThread:
    """记录 start/join 的假线程（不真正运行 target）."""

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
# 后台线程与连通性探测
# --------------------------------------------------------------------------- #
def test_auto_import_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """_auto_import 成功路径：置 importing=False 并触发 ping 事件."""
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
    """_auto_import 异常被记录且 finally 仍执行."""
    from src.knowledge import vocabulary

    def _boom() -> None:
        raise OSError("no network")

    monkeypatch.setattr(vocabulary, "init_db", _boom)
    monkeypatch.setattr(app_module, "_vocab_importing", True)
    with caplog.at_level("ERROR"):
        app_module._auto_import()
    assert app_module._vocab_importing is False
    assert "词库导入失败" in caplog.text


def test_ping_no_api_key_sets_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺少 api_key 的端点直接置 unknown."""
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
    """端点探测异常时置 error."""
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
    """端点探测成功时置 ok（不依赖真实配置/网络）."""
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
    """_auto_ping 执行一轮后阻塞等待事件（不再定时轮询），由 wait 异常退出."""
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
    # 关键：不再带 timeout 定时轮询（取消设置不会触发重探）
    assert waits and all(w is None for w in waits)


def test_start_background_threads_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """非测试环境下启动两条后台线程."""
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
    """测试环境下不启动后台线程."""
    _FakeThread.instances = []
    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setenv("STANZA_WEAVER_TEST", "1")
    app_module._start_background_threads()
    assert _FakeThread.instances == []


# --------------------------------------------------------------------------- #
# 自定义模板自动注册
# --------------------------------------------------------------------------- #
def test_register_custom_templates_dir_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Templates 目录不存在时提前返回."""
    monkeypatch.setattr(Path, "exists", lambda self: False)
    app_module._register_custom_templates()


def test_register_custom_templates_import_error(
    monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    """自定义模板加载失败仅记录日志."""
    fake = Path("src/templates/custom_nope.py")
    monkeypatch.setattr(Path, "glob", lambda self, pat: iter([fake]))
    monkeypatch.setattr(
        app_module,
        "_load_custom_template_module",
        lambda file_path: (_ for _ in ()).throw(ImportError("boom")),
    )
    with caplog.at_level("ERROR"):
        app_module._register_custom_templates()
    assert "自定义模板注册失败" in caplog.text


def test_custom_templates_dir_source_override_and_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """源码模式使用 src/templates；环境变量可覆盖；源码模式无旧目录."""
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
    """编译版使用用户数据目录，旧目录为安装目录；二者相同时返回 None."""
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
    """解析路径失败时仍返回旧目录（覆盖 OSError 兜底）."""
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
    """旧目录模板复制到新目录：跳过已存在/缺失/失败场景."""
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
    """从任意目录加载模板模块；执行失败清理 sys.modules."""
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
    """写一个最小可注册的自定义模板模块."""
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
    """编译版从用户数据目录加载自定义模板."""
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
    """编译版旧安装目录的模板迁移到用户目录并注册；用户目录版本优先."""
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

        # 用户目录中的同名模板优先于旧目录
        user_dir.mkdir(exist_ok=True)
        _write_custom_module(user_dir / "custom_testmod.py", "用户新版模板")
        app_module._register_custom_templates()
        assert _registry["custom_testmod"].name == "用户新版模板"
    finally:
        _registry.pop("custom_testmod", None)


def test_create_custom_template_in_user_dir_loads_generated_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """编译版目录下的生成模板可被加载（验证相对导入仍指向 src.templates）."""
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
    """编译版创建模板时写入用户数据目录."""
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
    """自定义模板成功加载并执行注册函数."""
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
# 模板顺序持久化 / 排序接口 / 删除接口
# --------------------------------------------------------------------------- #
def test_template_order_path_uses_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """顺序文件位于用户数据目录."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert app_module._template_order_path() == (
        tmp_path / ".stanza_weaver" / "template_order.json"
    )


def test_template_order_load_save_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """顺序文件读写与损坏兜底."""
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
    """测试环境跳过应用顺序；正式环境按文件应用；空顺序不调用."""
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
    """返回注册表当前 key 顺序."""
    from src.templates import _registry

    return list(_registry)


def _restore_order(snapshot: list[str]) -> None:
    """恢复注册表顺序."""
    from src.templates import set_order

    set_order(snapshot)


def test_reorder_templates_requires_csrf(client: FlaskClient) -> None:
    """排序接口需要 CSRF."""
    assert client.post("/api/templates/order", json={"order": []}).status_code == 403


def test_reorder_templates_invalid_body(client: FlaskClient) -> None:
    """排序接口请求体非法返回 400."""
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
    """排序接口重排注册表并持久化；未列出的模板追加在末尾."""
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
    """顺序文件写入失败返回 500."""
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
    """删除接口需要 CSRF."""
    assert client.post("/api/templates/delete", json={"key": "x"}).status_code == 403


def test_delete_template_invalid_body(client: FlaskClient) -> None:
    """删除接口请求体非法/缺少 key 返回 400."""
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
    """删除不存在的模板返回 404."""
    resp = client.post(
        "/api/templates/delete",
        json={"key": "custom_nope"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 404


def test_delete_template_builtin_rejected(client: FlaskClient) -> None:
    """内置模板不可删除."""
    resp = client.post(
        "/api/templates/delete",
        json={"key": "zh_wujue"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def _register_delete_dummy(key: str = "custom_delete_test") -> None:
    """注册一个可删除的测试模板."""
    from src.templates import PoetryTemplate, register

    class _Tpl(PoetryTemplate):
        """测试模板."""

        name = "删除测试"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    register(key, _Tpl())


def test_delete_template_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """删除自定义模板：移除注册、删除源码并更新时间顺序文件."""
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
    """源码文件不存在时仍可移除注册（容错）."""
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
    """删除源码失败返回 500 且保留注册."""
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
    """删除成功但顺序保存失败时仍返回成功（仅告警）."""
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
# 本地访问守卫 / i18n 兜底 / 配置写回
# --------------------------------------------------------------------------- #
def test_guard_local_access_rejects_foreign_host() -> None:
    """非本机 Host 返回 403."""
    with app_module.app.test_request_context("/", headers={"Host": "evil.example"}):
        resp = app_module._guard_local_access()
    assert resp is not None
    assert resp[1] == 403


def test_i18n_missing_language_falls_back(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """语言文件缺失时回退到 zh.yaml."""
    (tmp_path / "zh.yaml").write_text("html:\n  lang: zh-CN\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "_I18N_DIR", tmp_path)
    resp = client.get("/api/i18n/en")
    assert resp.status_code == 200
    assert resp.get_json()["html"]["lang"] == "zh-CN"


def test_config_post_requires_csrf(client: FlaskClient) -> None:
    """保存配置需要 CSRF."""
    assert client.post("/api/config", json={}).status_code == 403


def test_config_post_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """合法配置写回成功."""
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
    """非对象请求体返回 400."""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", data="not json", headers=_csrf_headers())
    assert resp.status_code == 400


def test_config_post_writer_not_dict(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Writer 配置不是对象返回 400."""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", json={"writer": "oops"}, headers=_csrf_headers())
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# SocketIO：generate 异常 / feedback / disconnect
# --------------------------------------------------------------------------- #
def test_generate_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate 线程中 pipeline 抛错时向前端推送 error."""

    class _Boom:
        def __init__(self) -> None:
            pass

        def run(self, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("src.pipeline.pipeline.PoetryPipeline", _Boom)
    sio = _sio_client()
    sio.emit("generate", {"topic": "主题", "template_key": "zh_wujue"})
    ev = _wait_event(sio, "error")
    assert "生成失败" in str(ev["args"])


def test_feedback_without_session_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """无活跃会话时 feedback 返回错误."""
    sio = _sio_client()
    sio.emit("feedback", {"feedback": "再婉约一些"})
    ev = _wait_event(sio, "error")
    assert "没有活跃的生成会话" in str(ev["args"])


def test_feedback_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feedback 线程中续跑抛错时向前端推送 error."""
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
    assert "反馈处理失败" in str(ev["args"])


def _patch_llm_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入桩 LLM 客户端（可驱动 generate + feedback 两轮）."""
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
    """Generate 定稿后 feedback 续跑再次定稿（同一会话）."""
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
    """断开连接时清理会话状态."""
    sio = _sio_client()
    sio.disconnect()


# --------------------------------------------------------------------------- #
# 自定义模板：源码构建与路由分支
# --------------------------------------------------------------------------- #
def test_build_custom_code_with_custom_code() -> None:
    """custom_code 被逐行缩进写入生成源码."""
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
    """创建自定义模板需要 CSRF."""
    assert client.post("/api/templates/custom", json={}).status_code == 403


def test_custom_template_not_dict(client: FlaskClient) -> None:
    """请求体非对象返回 400."""
    resp = client.post("/api/templates/custom", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_custom_template_invalid_lines(client: FlaskClient) -> None:
    """Lines 非数字且音节数与行数不符时返回 400."""
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
    """名称为空返回 400."""
    resp = client.post(
        "/api/templates/custom",
        json={"name": "", "language": "zh", "lines": 4, "syllables_per_line": [5] * 4},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_bad_syllables(client: FlaskClient) -> None:
    """音节数列表含非法元素返回 400."""
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
    """名称无法生成合法标识符时返回 400."""
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
    """模板文件写入失败返回 500."""

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
    assert "模板文件写入失败" in resp.get_json()["message"]


def test_custom_template_registration_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注册失败返回 500（写盘被 mock 为空操作，避免污染仓库）."""
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
    assert "注册失败" in resp.get_json()["message"]


def test_custom_template_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """成功创建并注册模板（写盘与注册均被 mock，避免污染仓库）."""
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
# 历史记录：非对象请求体
# --------------------------------------------------------------------------- #
def test_history_post_not_dict(client: FlaskClient) -> None:
    """保存历史记录时非对象请求体返回 400."""
    resp = client.post("/api/history", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_history_db_path_default_and_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """历史库路径：默认指向用户目录，set_history_db_path 可覆盖（供测试隔离）."""
    monkeypatch.setattr(app_module, "_HISTORY_DB_PATH", None)
    assert (
        app_module.get_history_db_path()
        == Path.home() / ".stanza_weaver" / "history.db"
    )
    app_module.set_history_db_path(tmp_path / "h.db")
    assert app_module.get_history_db_path() == tmp_path / "h.db"


# --------------------------------------------------------------------------- #
# 启动服务 / main / __main__
# --------------------------------------------------------------------------- #
def test_start_server_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认监听 127.0.0.1:5000."""
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
    """端口环境变量非法时回退 5000."""
    calls: list[Any] = []
    monkeypatch.setattr(
        app_module.socketio, "run", lambda *a, **k: calls.append((a, k))
    )
    monkeypatch.setenv("STANZAWEAVER_PORT", "abc")
    app_module.start_server()
    assert calls[0][1]["port"] == 5000


def test_main_import_webview_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Webview 不可导入时回退到 HTTP 服务."""
    calls: list[Any] = []
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(app_module, "start_server", lambda: calls.append("started"))
    app_module.main()
    assert calls == ["started"]


def test_main_webview_gui_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI 初始化失败时记录告警并等待后台服务线程."""
    _FakeThread.instances = []
    started: list[Any] = []

    class _Gui:
        def create_window(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("no display")

    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setitem(sys.modules, "webview", _Gui())
    monkeypatch.setattr(app_module, "start_server", lambda: started.append("server"))
    app_module.main()
    # HTTP 服务由后台线程承载（此处被假线程替换），失败路径仅等待该线程
    assert started == []
    assert len(_FakeThread.instances) == 1
    assert _FakeThread.instances[0].joined


def test_main_webview_gui_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI 正常启动."""
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
    """以 __main__ 方式执行 app.py 时覆盖入口守卫."""
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(SocketIO, "run", lambda self, *a, **k: None)
    runpy.run_path(str(Path(app_module.__file__)), run_name="__main__")
