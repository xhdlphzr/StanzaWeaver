# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""模板编辑 AI 的 app 层集成测试（自定义模板新字段/配置 editor/编辑模板 socket）.

全部使用桩 LLM 与临时写盘，避免真实网络请求与污染仓库。
"""

import inspect
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from flask.testing import FlaskClient

import app as app_module
from src.agents import editor_ai
from src.tools.template_tools import TemplateDraft


@pytest.fixture()
def client() -> Any:
    """提供 Flask 测试客户端."""
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf_headers() -> dict[str, str]:
    """返回含 CSRF 与 JSON 类型的请求头."""
    return {
        "X-CSRF-Token": app_module._CSRF_TOKEN,
        "Content-Type": "application/json",
    }


def _sio_client() -> Any:
    """创建 socketio 测试客户端."""
    return app_module.socketio.test_client(app_module.app)


_RECEIVED: dict[int, list[dict[str, Any]]] = {}


def _wait_event(sio: Any, name: str, timeout: float = 8.0) -> dict[str, Any]:
    """轮询等待某个 socket 事件（未匹配事件暂存，避免丢失）."""
    buffer = _RECEIVED.setdefault(id(sio), [])
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in list(buffer):
            if ev.get("name") == name:
                buffer.remove(ev)
                return ev
        buffer.extend(sio.get_received())
        time.sleep(0.02)
    raise AssertionError(f"no socket event: {name}")


def _cell(value: str = "") -> dict[str, Any]:
    """构造约束单元格."""
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": {"tone": value, "stress": "", "length": ""},
    }


# --------------------------------------------------------------------------- #
# 配置：editor 端点
# --------------------------------------------------------------------------- #
def test_config_get_includes_editor(client: FlaskClient) -> None:
    """GET /api/config 返回 editor 端点."""
    resp = client.get("/api/config", headers=_csrf_headers())
    data = resp.get_json()
    assert "editor" in data
    assert set(data["editor"]) == {"base_url", "api_key", "model"}


def test_config_save_editor(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/config 保存 editor 端点."""
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(
        app_module,
        "socketio",
        SimpleNamespace(emit=lambda *a, **k: saved.append(a)),
    )
    resp = client.post(
        "/api/config",
        json={
            "editor": {"base_url": "http://x", "api_key": "k", "model": "m"},
            "language": "zh",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    from src.config import get_config

    assert get_config().editor["base_url"] == "http://x"


def test_config_save_editor_invalid(client: FlaskClient) -> None:
    """POST /api/config editor 非 dict 返回 400."""
    resp = client.post("/api/config", json={"editor": "bad"}, headers=_csrf_headers())
    assert resp.status_code == 400


def test_llm_ping_includes_editor(client: FlaskClient) -> None:
    """手动 ping 包含 editor 状态."""
    resp = client.post("/api/llm-ping", headers=_csrf_headers())
    data = resp.get_json()
    assert "editor" in data


# --------------------------------------------------------------------------- #
# 模板源码生成：多约束 / 韵式
# --------------------------------------------------------------------------- #
def test_build_code_alternatives_and_rhyme() -> None:
    """多约束 + 韵式生成源码可编译且包含对应方法/调用."""
    alternatives = [
        [[_cell("平")]],
        [[_cell("仄")]],
    ]
    code = app_module._build_custom_template_code(
        name="多约束",
        language="zh",
        lines=1,
        syllables_per_line=[1],
        dimension="tone",
        constraints=alternatives[0],
        custom_code="errors.append('x')",
        class_name="CustomMultiTemplate",
        file_key="custom_multi",
        alternatives=alternatives,
        rhyme_scheme="A-",
        rhyme_distinct=True,
    )
    compile(code, "<custom_multi>", "exec")
    assert "get_syllable_constraint_alternatives" in code
    assert "from .rhyme import check_rhyme_scheme" in code
    assert "distinct=True" in code
    assert "2 种可选音节约束" in code
    assert "errors.append('x')" in code
    assert 'rhyme_scheme = "A-"' in code
    assert "custom_code" in code


def test_build_code_empty_tables() -> None:
    """无约束时生成空表源码且可编译（含非列表行的容错）."""
    code = app_module._build_custom_template_code(
        name="空",
        language="fr",
        lines=1,
        syllables_per_line=[1],
        dimension="",
        constraints=[],
        custom_code="",
        class_name="CustomEmptyTemplate",
        file_key="custom_empty",
        alternatives=None,
    )
    compile(code, "<custom_empty>", "exec")
    assert "def get_syllable_constraints" in code

    code2 = app_module._build_custom_template_code(
        name="空2",
        language="zh",
        lines=1,
        syllables_per_line=[1],
        dimension="tone",
        constraints=[[_cell("平")], "bad-row"],
        custom_code="",
        class_name="CustomEmpty2Template",
        file_key="custom_empty2",
    )
    compile(code2, "<custom_empty2>", "exec")


# --------------------------------------------------------------------------- #
# 落盘注册助手
# --------------------------------------------------------------------------- #
def _patch_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """把模板写盘替换为空操作."""
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)


def _patch_register(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """把模板模块加载替换为返回带注册函数的命名空间."""

    def _fake_load(file_path: Path) -> Any:
        name = f"src.templates.{file_path.stem}"
        register_name = file_path.stem.replace("custom_", "register_custom_")
        return SimpleNamespace(**{register_name: lambda: calls.append(name)})

    monkeypatch.setattr(app_module, "_load_custom_template_module", _fake_load)


def test_create_custom_template_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """_create_custom_template 成功返回 200 与 key."""
    calls: list[str] = []
    emitted: list[Any] = []
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, calls)
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: emitted.append(a))
    status, payload = app_module._create_custom_template(
        name="新模板",
        language="zh",
        lines=1,
        syllables_per_line=[2],
        alternatives=[[[_cell("平"), _cell()]]],
        custom_code="",
    )
    assert status == 200
    assert payload["key"] == "custom_新模板"
    assert any(e[0] == "templates_updated" for e in emitted)


def test_create_custom_template_bad_name() -> None:
    """模板名无法生成标识符时返回 400."""
    status, payload = app_module._create_custom_template(
        name="!!!",
        language="zh",
        lines=1,
        syllables_per_line=[2],
        alternatives=[[]],
        custom_code="",
    )
    assert status == 400
    assert "模板名" in payload["message"]


def test_create_custom_template_bad_rhyme_scheme() -> None:
    """落盘助手校验韵式，长度不符返回 400."""
    status, payload = app_module._create_custom_template(
        name="坏韵式",
        language="zh",
        lines=2,
        syllables_per_line=[2, 2],
        alternatives=[[]],
        custom_code="",
        rhyme_scheme="ABAB",
    )
    assert status == 400
    assert "韵式" in payload["message"]


def test_create_custom_template_write_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """写盘失败返回 500."""

    def _raise(self: Any, *a: Any, **k: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _raise)
    status, payload = app_module._create_custom_template(
        name="写失败",
        language="zh",
        lines=1,
        syllables_per_line=[1],
        alternatives=[[]],
        custom_code="",
    )
    assert status == 500
    assert "写入失败" in payload["message"]


def test_create_custom_template_register_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """注册失败返回 500."""
    _patch_write(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "_load_custom_template_module",
        lambda file_path: (_ for _ in ()).throw(ImportError("boom")),
    )
    status, payload = app_module._create_custom_template(
        name="注册失败",
        language="zh",
        lines=1,
        syllables_per_line=[1],
        alternatives=[[]],
        custom_code="",
    )
    assert status == 500
    assert "注册失败" in payload["message"]


def test_create_custom_template_from_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 草稿可直接落盘注册."""
    calls: list[str] = []
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, calls)
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    draft = TemplateDraft(name="AI模板", language="zh", lines=1)
    draft.syllables_per_line = [2]
    draft.alternatives = [[["平", ""]]]
    status, payload = app_module._create_custom_template_from_draft(draft)
    assert status == 200
    assert payload["key"] == "custom_AI模板"


# --------------------------------------------------------------------------- #
# 创建模板路由：新字段
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 统一转化接口
# --------------------------------------------------------------------------- #
def test_convert_requires_csrf(client: FlaskClient) -> None:
    """转化接口需要 CSRF 令牌."""
    assert client.post("/api/templates/convert", json={}).status_code == 403


def test_convert_not_dict(client: FlaskClient) -> None:
    """请求体非对象返回 400."""
    resp = client.post("/api/templates/convert", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_convert_missing_base_key(client: FlaskClient) -> None:
    """缺少源模板 key 返回 400."""
    resp = client.post(
        "/api/templates/convert", json={"language": "en"}, headers=_csrf_headers()
    )
    assert resp.status_code == 400
    assert "源模板" in resp.get_json()["message"]


def test_convert_unknown_key(client: FlaskClient) -> None:
    """未知源模板返回 400."""
    resp = client.post(
        "/api/templates/convert",
        json={"base_template_key": "nope", "language": "en"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_convert_bad_language(client: FlaskClient) -> None:
    """未知目标语言返回 400."""
    resp = client.post(
        "/api/templates/convert",
        json={"base_template_key": "en_sonnet", "language": "xx"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_convert_bad_mapping(client: FlaskClient) -> None:
    """非法映射返回 400."""
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "en_sonnet",
            "language": "zh",
            "mapping": {"??": "平"},
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_convert_success_carries_rhyme(client: FlaskClient) -> None:
    """转化成功：音节约束按映射转换、韵式与代码一并复制."""
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_xiangjianhuan",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["language"] == "en"
    assert data["lines"] == 7
    assert data["rhyme_scheme"] == "AAABBAA"
    assert data["source_name"] == "相见欢"
    values = {
        cell["attributes"]["stress"]
        for table in data["alternatives"]
        for row in table
        for cell in row
        if cell["attributes"]["stress"]
    }
    assert values <= {"heavy", "light"} and values


def test_convert_success_for_custom_template(
    client: FlaskClient,
) -> None:
    """转化自定义模板时自定义代码也被复制（用注册表临时模板）."""
    from src.templates import PoetryTemplate, _registry, register

    class _WithCode(PoetryTemplate):
        """带自定义代码的临时模板."""

        name = "带代码模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        rhyme_scheme = "A"
        custom_code = "errors.append('x')"

        def get_syllable_constraints(self) -> Any:
            """逐位约束."""
            return [
                [
                    {
                        "onset": "",
                        "nucleus": "",
                        "coda": "",
                        "attributes": {"tone": "平", "stress": "", "length": ""},
                    },
                    {
                        "onset": "",
                        "nucleus": "",
                        "coda": "",
                        "attributes": {"tone": "", "stress": "", "length": ""},
                    },
                ]
            ]

    register("test_route_with_code", _WithCode())
    try:
        resp = client.post(
            "/api/templates/convert",
            json={
                "base_template_key": "test_route_with_code",
                "language": "en",
                "mapping": {"平": "heavy"},
            },
            headers=_csrf_headers(),
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["rhyme_scheme"] == "A"
        assert data["code"] == "errors.append('x')"
    finally:
        _registry.pop("test_route_with_code", None)


def test_convert_success_jinti_structural(client: FlaskClient) -> None:
    """转化绝句：三平尾/孤平/平仄骨架等结构规则随数据携带并按映射换值."""
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    rules = data["structural_rules"]
    assert rules["attribute"] == "stress"
    assert rules["level_value"] == "heavy"
    assert rules["oblique_value"] == "light"
    assert rules["forbid_sanpingwei"] is True
    assert rules["forbid_guping"] is True
    assert "jinti" in data["carried_rules"]
    assert data["dropped_rules"] == []
    assert "格律规则" in data["rule_note"]
    assert "rule_note" in data["carried_rules"]


def _structural_rules() -> dict[str, Any]:
    """构造一份合法的数据化近体诗结构规则."""
    return {
        "kind": "jinti",
        "attribute": "tone",
        "level_value": "平",
        "oblique_value": "仄",
        "positions": [1, 3],
        "rhyme_lines": [1, 3],
        "optional_first_rhyme": True,
        "forbid_sanpingwei": True,
        "forbid_guping": True,
    }


def test_build_code_with_structural_rules() -> None:
    """带结构规则的模板源码：导入/引用 check_jinti_rules 且不再生成通用押韵调用."""
    alternatives = [[[_cell("平"), _cell()], [_cell("仄"), _cell()]]]
    code = app_module._build_custom_template_code(
        name="数据化结构",
        language="zh",
        lines=2,
        syllables_per_line=[2, 2],
        dimension="tone",
        constraints=alternatives[0],
        custom_code="",
        class_name="CustomStructTemplate",
        file_key="custom_struct",
        alternatives=alternatives,
        rhyme_scheme="AA",
        rhyme_distinct=False,
        structural_rules=_structural_rules(),
    )
    compile(code, "<custom_struct>", "exec")
    assert "from .structural import check_jinti_rules" in code
    assert "check_jinti_rules(" in code
    assert '"forbid_sanpingwei": True' in code or "'forbid_sanpingwei': True" in code
    assert "check_rhyme_scheme" not in code


def test_build_code_with_rule_note() -> None:
    """模板规则描述写入生成源码的 rule_note 类属性."""
    code = app_module._build_custom_template_code(
        name="带描述",
        language="zh",
        lines=1,
        syllables_per_line=[2],
        dimension="tone",
        constraints=[[_cell("平"), _cell()]],
        custom_code="",
        class_name="CustomNoteTemplate",
        file_key="custom_note",
        rule_note="上下联需对仗，意境清远。",
    )
    compile(code, "<custom_note>", "exec")
    assert "rule_note = " in code
    assert "上下联需对仗，意境清远。" in code


def test_route_create_with_rule_note(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """创建路由接受规则描述并写入源码；超长时返回 400."""
    captured: list[str] = []

    def _capture(self: Any, data: str, *a: Any, **k: Any) -> None:
        captured.append(data)

    monkeypatch.setattr(Path, "write_text", _capture)
    _patch_register(monkeypatch, [])
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "带规则描述",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [2],
            "constraints": [[_cell("平"), _cell()]],
            "rule_note": "注意对仗与领字",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    assert captured and "注意对仗与领字" in captured[0]
    too_long = client.post(
        "/api/templates/custom",
        json={
            "name": "描述过长",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [2],
            "rule_note": "x" * 4001,
        },
        headers=_csrf_headers(),
    )
    assert too_long.status_code == 400


def test_convert_route_carries_rule_note(client: FlaskClient) -> None:
    """转化接口复制源模板规则描述并报告已携带."""
    from src.templates import PoetryTemplate, _registry, register

    class _Note(PoetryTemplate):
        """带规则描述的临时模板."""

        name = "带描述来源"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "注意对仗"

        def get_syllable_constraints(self) -> Any:
            """一份自由约束."""
            return [[_cell("")]]

    register("test_route_note", _Note())
    try:
        resp = client.post(
            "/api/templates/convert",
            json={"base_template_key": "test_route_note", "language": "en"},
            headers=_csrf_headers(),
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["rule_note"] == "注意对仗"
        assert "rule_note" in data["carried_rules"]
    finally:
        _registry.pop("test_route_note", None)


def test_create_custom_template_with_structural_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """带结构规则的模板可落盘注册（写盘与导入被 mock）."""
    calls: list[str] = []
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, calls)
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    status, payload = app_module._create_custom_template(
        name="结构规则模板",
        language="zh",
        lines=2,
        syllables_per_line=[2, 2],
        alternatives=[[[_cell("平"), _cell()], [_cell("仄"), _cell()]]],
        custom_code="",
        rhyme_scheme="AA",
        structural_rules=_structural_rules(),
    )
    assert status == 200
    assert payload["key"]
    assert calls


def test_create_custom_template_invalid_structural_rules() -> None:
    """非法结构规则返回 400."""
    status, payload = app_module._create_custom_template(
        name="坏结构",
        language="zh",
        lines=2,
        syllables_per_line=[2, 2],
        alternatives=[[]],
        custom_code="",
        structural_rules={"kind": "bad"},
    )
    assert status == 400
    assert "结构规则" in payload["message"]


def test_route_create_with_structural_rules(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """创建模板路由接受并校验 structural_rules."""
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, [])
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "路由结构规则",
            "language": "zh",
            "lines": 2,
            "syllables_per_line": [2, 2],
            "constraints": [[_cell("平"), _cell()], [_cell("仄"), _cell()]],
            "rhyme_scheme": "AA",
            "structural_rules": _structural_rules(),
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    bad = client.post(
        "/api/templates/custom",
        json={
            "name": "路由坏结构",
            "language": "zh",
            "lines": 2,
            "syllables_per_line": [2, 2],
            "structural_rules": {"kind": "bad"},
        },
        headers=_csrf_headers(),
    )
    assert bad.status_code == 400


def test_create_from_draft_keeps_structural_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 草稿落盘时结构规则写入生成源码."""
    captured: list[str] = []

    def _capture_write(self: Any, data: str, *a: Any, **k: Any) -> None:
        captured.append(data)

    monkeypatch.setattr(Path, "write_text", _capture_write)
    _patch_register(monkeypatch, [])
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    draft = TemplateDraft(name="AI结构", language="zh", lines=2)
    draft.syllables_per_line = [2, 2]
    draft.alternatives = [[["平", ""], ["仄", ""]]]
    draft.structural_rules = _structural_rules()
    draft.rule_note = "注意情景交融"
    status, payload = app_module._create_custom_template_from_draft(draft)
    assert status == 200
    assert payload["key"]
    assert captured and "check_jinti_rules" in captured[0]
    assert "注意情景交融" in captured[0]


# --------------------------------------------------------------------------- #
# 源模板代码提取 / AI 代码转写选项
# --------------------------------------------------------------------------- #
def test_template_source_code_builtin() -> None:
    """内置模板源码包含类定义与其规则辅助函数."""
    from src.templates import get

    code = app_module._template_source_code("zh_wujue", get("zh_wujue"))
    assert "class WujueTemplate" in code
    assert "_check_jinti_full" in code
    assert "_TONGYUN = " in code


def test_template_source_code_builtin_inspect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无法读取类源码时返回空串."""
    from src.templates import get

    monkeypatch.setattr(
        inspect,
        "getsource",
        lambda obj: (_ for _ in ()).throw(OSError("x")),
    )
    assert app_module._template_source_code("zh_wujue", get("zh_wujue")) == ""


def test_template_source_code_custom_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """自定义模板优先读取落盘源码."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """测试模板."""

        name = "源码模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    register("custom_src_test", _Tpl())
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "custom_src_test.py").write_text("SOURCE_CODE", encoding="utf-8")
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    try:
        assert (
            app_module._template_source_code(
                "custom_src_test", _registry["custom_src_test"]
            )
            == "SOURCE_CODE"
        )
    finally:
        _registry.pop("custom_src_test", None)


def test_template_source_code_custom_read_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """读取模板源码失败时回退到按规格重建."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """测试模板."""

        name = "读取失败模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    register("custom_read_fail", _Tpl())
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "custom_read_fail.py").write_text("SOURCE", encoding="utf-8")
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: templates_dir)
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: (_ for _ in ()).throw(OSError("denied")),
    )
    try:
        code = app_module._template_source_code(
            "custom_read_fail", _registry["custom_read_fail"]
        )
        assert "class CustomReadFailTemplate" in code
    finally:
        _registry.pop("custom_read_fail", None)


def test_template_source_code_builtin_helper_source_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """辅助函数源码读取失败时跳过该函数（类源码仍保留）."""
    from src.templates import get

    real_getsource = inspect.getsource

    def _getsource(obj: Any) -> str:
        if inspect.isclass(obj):
            return real_getsource(obj)
        raise TypeError("no source")

    monkeypatch.setattr(inspect, "getsource", _getsource)
    code = app_module._template_source_code("zh_wujue", get("zh_wujue"))
    assert "class WujueTemplate" in code


def test_template_source_code_custom_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """源码文件缺失时按模板规格重建源码."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """测试模板."""

        name = "重建模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

        def get_syllable_constraints(self) -> Any:
            """一份约束表."""
            return [
                [
                    _cell(""),
                ]
            ]

    register("custom_rebuild_test", _Tpl())
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    try:
        code = app_module._template_source_code(
            "custom_rebuild_test", _registry["custom_rebuild_test"]
        )
        assert "class CustomRebuildTestTemplate" in code
        assert "_make_syl" in code
    finally:
        _registry.pop("custom_rebuild_test", None)


def test_template_source_code_custom_fallback_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """源码重建异常时返回空串（AI 转写降级）."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """to_dict 会失败的测试模板."""

        name = "坏模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

        def to_dict(self) -> dict[str, Any]:
            """始终抛异常."""
            raise RuntimeError("boom")

    register("custom_bad_test", _Tpl())
    monkeypatch.setattr(app_module, "_custom_templates_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(app_module, "_legacy_custom_templates_dir", lambda: None)
    try:
        assert (
            app_module._template_source_code(
                "custom_bad_test", _registry["custom_bad_test"]
            )
            == ""
        )
    finally:
        _registry.pop("custom_bad_test", None)


def _patch_ai_rewriter(monkeypatch: pytest.MonkeyPatch, result: Any) -> dict[str, Any]:
    """替换 TemplateCodeRewriter 并记录调用参数."""
    record: dict[str, Any] = {}
    fake_class: Any

    if isinstance(result, Exception):

        class fake_class:  # type: ignore[no-redef]
            """抛异常的桩."""

            def __init__(self, config: dict[str, Any]) -> None:
                record["config"] = config

            def rewrite(self, **kwargs: Any) -> dict[str, Any]:
                record["kwargs"] = kwargs
                raise result

    else:

        class fake_class:  # type: ignore[no-redef]
            """返回预置结果的桩."""

            def __init__(self, config: dict[str, Any]) -> None:
                record["config"] = config

            def rewrite(self, **kwargs: Any) -> dict[str, Any]:
                record["kwargs"] = kwargs
                return dict(result)

    monkeypatch.setattr("src.agents.editor_ai.TemplateCodeRewriter", fake_class)
    return record


def _editor_config(api_key: str = "k") -> SimpleNamespace:
    """构造模板 AI 配置."""
    return SimpleNamespace(
        editor={"base_url": "http://x", "api_key": api_key, "model": "m"}
    )


def test_convert_with_ai_rewrite_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """勾选 AI 转写时用返回代码替换确定性代码."""
    monkeypatch.setattr("src.config.get_config", lambda: _editor_config())
    monkeypatch.setattr(app_module, "_template_source_code", lambda key, tpl: "SOURCE")
    record = _patch_ai_rewriter(
        monkeypatch,
        {"status": "ok", "code": "errors.append('ai')", "notes": "note"},
    )
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
            "ai_rewrite_code": True,
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ai_rewrite_applied"] is True
    assert data["code"] == "errors.append('ai')"
    assert data["ai_rewrite_notes"] == "note"
    assert "ai_code" in data["carried_rules"]
    assert record["kwargs"]["source_code"] == "SOURCE"
    assert record["kwargs"]["mapping"] == {"平": "heavy", "仄": "light"}
    assert record["kwargs"]["source_language"] == "zh"
    assert record["kwargs"]["target_language"] == "en"


def test_convert_with_ai_rewrite_requires_api_key(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模板 AI 未配置时降级为确定性结果并给出错误信息."""
    monkeypatch.setattr("src.config.get_config", lambda: _editor_config(""))
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
            "ai_rewrite_code": True,
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ai_rewrite_applied"] is False
    assert "未配置" in data["ai_rewrite_error"]


def test_convert_with_ai_rewrite_source_unavailable(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无法提取源码时降级并提示."""
    monkeypatch.setattr("src.config.get_config", lambda: _editor_config())
    monkeypatch.setattr(app_module, "_template_source_code", lambda key, tpl: "")
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
            "ai_rewrite_code": True,
        },
        headers=_csrf_headers(),
    )
    assert "无法获取源模板代码" in resp.get_json()["ai_rewrite_error"]


def test_convert_with_ai_rewrite_error_and_exception(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI 返回错误或异常时降级并提示."""
    monkeypatch.setattr("src.config.get_config", lambda: _editor_config())
    monkeypatch.setattr(app_module, "_template_source_code", lambda key, tpl: "SOURCE")
    _patch_ai_rewriter(monkeypatch, {"status": "error", "message": "转写失败原因"})
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
            "ai_rewrite_code": True,
        },
        headers=_csrf_headers(),
    )
    assert "转写失败原因" in resp.get_json()["ai_rewrite_error"]

    _patch_ai_rewriter(monkeypatch, RuntimeError("boom"))
    resp = client.post(
        "/api/templates/convert",
        json={
            "base_template_key": "zh_wujue",
            "language": "en",
            "mapping": {"平": "heavy", "仄": "light"},
            "ai_rewrite_code": True,
        },
        headers=_csrf_headers(),
    )
    assert "模板代码 AI 转写失败" in resp.get_json()["ai_rewrite_error"]


def test_route_create_with_alternatives_and_rhyme(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """路由接受 alternatives / rhyme_scheme / rhyme_distinct."""
    calls: list[str] = []
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, calls)
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "路由多约束",
            "language": "zh",
            "lines": 2,
            "syllables_per_line": [2, 2],
            "constraints": [[_cell("平"), _cell()], [_cell("仄"), _cell()]],
            "alternatives": [
                [[_cell("平"), _cell()], [_cell("仄"), _cell()]],
                [[_cell("仄"), _cell()], [_cell("平"), _cell()]],
            ],
            "rhyme_scheme": "AA",
            "rhyme_distinct": True,
            "code": "",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert calls


def test_route_create_bad_rhyme_scheme(client: FlaskClient) -> None:
    """韵式长度不符返回 400."""
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "坏韵式",
            "language": "zh",
            "lines": 4,
            "syllables_per_line": [5, 5, 5, 5],
            "constraints": [],
            "rhyme_scheme": "AB",
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400
    assert "韵式" in resp.get_json()["message"]


def test_route_create_alternatives_with_non_list_entries(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alternatives 中的非列表项被容错为空表."""
    _patch_write(monkeypatch)
    _patch_register(monkeypatch, [])
    monkeypatch.setattr(app_module.socketio, "emit", lambda *a, **k: None)
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "容错约束",
            "language": "zh",
            "lines": 1,
            "syllables_per_line": [1],
            "alternatives": ["bad"],
            "constraints": [],
        },
        headers=_csrf_headers(),
    )
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# 编辑模板 socket
# --------------------------------------------------------------------------- #
def test_edit_template_requires_prompt() -> None:
    """空 prompt 直接返回错误."""
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": " ", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"


def test_edit_template_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """模板AI 未配置 API Key 时返回错误."""
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(editor={"base_url": "u", "api_key": "", "model": "m"}),
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"
    assert "API Key" in done["args"][0]["message"]


def _patch_editor_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """把配置替换为已填 API Key 的 editor 端点."""
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(editor={"base_url": "u", "api_key": "k", "model": "m"}),
    )


def _fake_editor(
    *, submitted: bool, message: str = "完成", fail: bool = False
) -> type[Any]:
    """构造假的模板编辑 AI 类."""

    class _Fake:
        def __init__(self, config: dict[str, Any]) -> None:
            self.config = config

        def edit(
            self,
            prompt: str,
            payload: dict[str, Any] | None = None,
            emit: Any = None,
            max_rounds: int = 12,
        ) -> editor_ai.EditorResult:
            if fail:
                raise RuntimeError("boom")
            if emit:
                emit({"type": "message", "content": "好的"})
            draft = TemplateDraft(name="AI模板", language="zh", lines=1)
            draft.syllables_per_line = [2]
            draft.alternatives = [[["平", ""]]]
            return editor_ai.EditorResult(draft, submitted, message)

    return _Fake


def test_edit_template_applies_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 未提交时返回草稿供前端回填（含事件推送）."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(editor_ai, "TemplateEditorAI", _fake_editor(submitted=False))
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": "bad"})
    event = _wait_event(sio, "template_ai")
    assert event["args"][0]["type"] == "message"
    done = _wait_event(sio, "template_ai_done")
    payload = done["args"][0]
    assert payload["status"] == "ok"
    assert payload["created_key"] is None
    assert payload["draft"]["name"] == "AI模板"


def test_edit_template_submitted_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 调用提交后服务端创建模板并返回 created_key."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(editor_ai, "TemplateEditorAI", _fake_editor(submitted=True))
    monkeypatch.setattr(
        app_module,
        "_create_custom_template_from_draft",
        lambda draft: (200, {"key": "custom_ai", "message": "已创建"}),
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    payload = done["args"][0]
    assert payload["status"] == "ok"
    assert payload["created_key"] == "custom_ai"


def test_edit_template_submitted_create_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 提交后创建失败时返回错误."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(editor_ai, "TemplateEditorAI", _fake_editor(submitted=True))
    monkeypatch.setattr(
        app_module,
        "_create_custom_template_from_draft",
        lambda draft: (500, {"message": "注册失败: boom"}),
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    payload = done["args"][0]
    assert payload["status"] == "error"
    assert "注册失败" in payload["message"]


def test_edit_template_agent_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 代理异常时返回错误事件."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(
        editor_ai, "TemplateEditorAI", _fake_editor(submitted=False, fail=True)
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"
    assert "处理失败" in done["args"][0]["message"]
