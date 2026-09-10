# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""app.py 补齐覆盖：后台线程/连通性探测/自定义模板落盘/配置写回/反馈续跑等。

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
    """提供 Flask 测试客户端。"""
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf() -> dict[str, str]:
    """返回 CSRF 请求头。"""
    return {"X-CSRF-Token": app_module._CSRF_TOKEN}


def _csrf_headers() -> dict[str, str]:
    """返回含 CSRF 与 JSON 类型的请求头。"""
    return {**_csrf(), "Content-Type": "application/json"}


def _wait_event(sio: Any, name: str, timeout: float = 8.0) -> dict[str, Any]:
    """轮询等待某个 socket 事件。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in sio.get_received():
            if ev.get("name") == name:
                return cast(dict[str, Any], ev)
        time.sleep(0.02)
    raise AssertionError(f"no socket event: {name}")


def _sio_client() -> Any:
    """创建 socketio 测试客户端。"""
    return app_module.socketio.test_client(app_module.app)


class _FakeThread:
    """记录 start/join 的假线程（不真正运行 target）。"""

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
    """_auto_import 成功路径：置 importing=False 并触发 ping 事件。"""
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
    """_auto_import 异常被记录且 finally 仍执行。"""
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
    """缺少 api_key 的端点直接置 unknown。"""
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
    """端点探测异常时置 error。"""
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
    """端点探测成功时置 ok（不依赖真实配置/网络）。"""
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
    """_auto_ping 执行完整一轮（含 clear）后由 wait 异常退出。"""
    emitted: list[tuple[str, Any]] = []
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: emitted.append(a))
    monkeypatch.setattr(app_module, "_ping_one_endpoint", lambda name: None)

    class _FakeEvent:
        def __init__(self) -> None:
            self.calls = 0
            self.cleared = 0

        def wait(self, timeout: float = 0) -> None:
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


def test_start_background_threads_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """非测试环境下启动两条后台线程。"""
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
    """测试环境下不启动后台线程。"""
    _FakeThread.instances = []
    monkeypatch.setattr("threading.Thread", _FakeThread)
    monkeypatch.setenv("STANZA_WEAVER_TEST", "1")
    app_module._start_background_threads()
    assert _FakeThread.instances == []


# --------------------------------------------------------------------------- #
# 自定义模板自动注册
# --------------------------------------------------------------------------- #
def test_register_custom_templates_dir_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """templates 目录不存在时提前返回。"""
    monkeypatch.setattr(Path, "exists", lambda self: False)
    app_module._register_custom_templates()


def test_register_custom_templates_import_error(
    monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    """自定义模板导入失败仅记录日志。"""
    import importlib

    fake = Path("src/templates/custom_nope.py")
    monkeypatch.setattr(Path, "glob", lambda self, pat: iter([fake]))
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("boom")),
    )
    with caplog.at_level("ERROR"):
        app_module._register_custom_templates()
    assert "自定义模板注册失败" in caplog.text


def test_register_custom_templates_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义模板成功导入并执行注册函数。"""
    import importlib

    calls: list[str] = []
    fake = Path("src/templates/custom_hit.py")

    def _fake_import(name: str) -> Any:
        mod = SimpleNamespace()
        mod.register_custom_hit = lambda: calls.append(name)
        return mod

    monkeypatch.setattr(Path, "glob", lambda self, pat: iter([fake]))
    monkeypatch.setattr(importlib, "import_module", _fake_import)
    app_module._register_custom_templates()
    assert calls == ["src.templates.custom_hit"]


# --------------------------------------------------------------------------- #
# 本地访问守卫 / i18n 兜底 / 配置写回
# --------------------------------------------------------------------------- #
def test_guard_local_access_rejects_foreign_host() -> None:
    """非本机 Host 返回 403。"""
    with app_module.app.test_request_context("/", headers={"Host": "evil.example"}):
        resp = app_module._guard_local_access()
    assert resp is not None
    assert resp[1] == 403


def test_i18n_missing_language_falls_back(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """语言文件缺失时回退到 zh.yaml。"""
    (tmp_path / "zh.yaml").write_text("html:\n  lang: zh-CN\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "_I18N_DIR", tmp_path)
    resp = client.get("/api/i18n/en")
    assert resp.status_code == 200
    assert resp.get_json()["html"]["lang"] == "zh-CN"


def test_config_post_requires_csrf(client: FlaskClient) -> None:
    """保存配置需要 CSRF。"""
    assert client.post("/api/config", json={}).status_code == 403


def test_config_post_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """合法配置写回成功。"""
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
    """非对象请求体返回 400。"""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", data="not json", headers=_csrf_headers())
    assert resp.status_code == 400


def test_config_post_writer_not_dict(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """writer 配置不是对象返回 400。"""
    cfg = Config(tmp_path / "cfg.json")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    resp = client.post("/api/config", json={"writer": "oops"}, headers=_csrf_headers())
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# SocketIO：generate 异常 / feedback / disconnect
# --------------------------------------------------------------------------- #
def test_generate_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """generate 线程中 pipeline 抛错时向前端推送 error。"""

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
    """无活跃会话时 feedback 返回错误。"""
    sio = _sio_client()
    sio.emit("feedback", {"feedback": "再婉约一些"})
    ev = _wait_event(sio, "error")
    assert "没有活跃的生成会话" in str(ev["args"])


def test_feedback_pipeline_error_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """feedback 线程中续跑抛错时向前端推送 error。"""
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
    """注入桩 LLM 客户端（可驱动 generate + feedback 两轮）。"""
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
    """generate 定稿后 feedback 续跑再次定稿（同一会话）。"""
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
    """断开连接时清理会话状态。"""
    sio = _sio_client()
    sio.disconnect()


# --------------------------------------------------------------------------- #
# 自定义模板：源码构建与路由分支
# --------------------------------------------------------------------------- #
def test_build_custom_code_with_custom_code() -> None:
    """custom_code 被逐行缩进写入生成源码。"""
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
    """创建自定义模板需要 CSRF。"""
    assert client.post("/api/templates/custom", json={}).status_code == 403


def test_custom_template_not_dict(client: FlaskClient) -> None:
    """请求体非对象返回 400。"""
    resp = client.post("/api/templates/custom", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_custom_template_invalid_lines(client: FlaskClient) -> None:
    """lines 非数字且音节数与行数不符时返回 400。"""
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
    """名称为空返回 400。"""
    resp = client.post(
        "/api/templates/custom",
        json={"name": "", "language": "zh", "lines": 4, "syllables_per_line": [5] * 4},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_custom_template_bad_syllables(client: FlaskClient) -> None:
    """音节数列表含非法元素返回 400。"""
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
    """名称无法生成合法标识符时返回 400。"""
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
    """模板文件写入失败返回 500。"""

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
    """注册失败返回 500（写盘被 mock 为空操作，避免污染仓库）。"""
    import importlib

    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("boom")),
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
    """成功创建并注册模板（写盘与注册均被 mock，避免污染仓库）。"""
    import importlib

    calls: list[str] = []
    emitted: list[Any] = []
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: SimpleNamespace(register_custom_ok=lambda: calls.append(name)),
    )
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
    assert calls == ["src.templates.custom_ok"]
    assert any(e[0] == "templates_updated" for e in emitted)


# --------------------------------------------------------------------------- #
# 历史记录：非对象请求体
# --------------------------------------------------------------------------- #
def test_history_post_not_dict(client: FlaskClient) -> None:
    """保存历史记录时非对象请求体返回 400。"""
    resp = client.post("/api/history", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# 启动服务 / main / __main__
# --------------------------------------------------------------------------- #
def test_start_server_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认监听 127.0.0.1:5000。"""
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
    """端口环境变量非法时回退 5000。"""
    calls: list[Any] = []
    monkeypatch.setattr(
        app_module.socketio, "run", lambda *a, **k: calls.append((a, k))
    )
    monkeypatch.setenv("STANZAWEAVER_PORT", "abc")
    app_module.start_server()
    assert calls[0][1]["port"] == 5000


def test_main_import_webview_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """webview 不可导入时回退到 HTTP 服务。"""
    calls: list[Any] = []
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(app_module, "start_server", lambda: calls.append("started"))
    app_module.main()
    assert calls == ["started"]


def test_main_webview_gui_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI 初始化失败时记录告警并等待后台服务线程。"""
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
    """GUI 正常启动。"""
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
    """以 __main__ 方式执行 app.py 时覆盖入口守卫。"""
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(SocketIO, "run", lambda self, *a, **k: None)
    runpy.run_path(str(Path(app_module.__file__)), run_name="__main__")
