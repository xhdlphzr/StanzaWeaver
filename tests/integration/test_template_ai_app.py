# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""App-level integration tests for the template-editing AI.

Covers new custom-template fields, editor config, and the edit-template socket.
All flows use stub LLMs and temp writes: no real network, no repo pollution.
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
    """Provide a Flask test client."""
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf_headers() -> dict[str, str]:
    """Return request headers with CSRF and JSON content type."""
    return {
        "X-CSRF-Token": app_module._CSRF_TOKEN,
        "Content-Type": "application/json",
    }


def _sio_client() -> Any:
    """Create a SocketIO test client."""
    return app_module.socketio.test_client(app_module.app)


_RECEIVED: dict[int, list[dict[str, Any]]] = {}


def _wait_event(sio: Any, name: str, timeout: float = 8.0) -> dict[str, Any]:
    """Poll for a socket event, buffering unmatched events so none are lost."""
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
    """Build a constraint cell."""
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": {"tone": value, "stress": "", "length": ""},
    }


# --------------------------------------------------------------------------- #
# Config: editor endpoint
# --------------------------------------------------------------------------- #
def test_config_get_includes_editor(client: FlaskClient) -> None:
    """GET /api/config returns the editor endpoint."""
    resp = client.get("/api/config", headers=_csrf_headers())
    data = resp.get_json()
    assert "editor" in data
    assert set(data["editor"]) == {"base_url", "api_key", "model"}


def test_config_save_editor(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/config saves the editor endpoint."""
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
    """POST /api/config with a non-dict editor returns 400."""
    resp = client.post("/api/config", json={"editor": "bad"}, headers=_csrf_headers())
    assert resp.status_code == 400


def test_llm_ping_includes_editor(client: FlaskClient) -> None:
    """A manual ping includes the editor status."""
    resp = client.post("/api/llm-ping", headers=_csrf_headers())
    data = resp.get_json()
    assert "editor" in data


# --------------------------------------------------------------------------- #
# Template source generation: multiple constraints / rhyme
# --------------------------------------------------------------------------- #
def test_build_code_alternatives_and_rhyme() -> None:
    """Multi-constraint + rhyme source compiles and includes the expected calls."""
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
    assert "syllable-constraint variants" in code
    assert "errors.append('x')" in code
    assert 'rhyme_scheme = "A-"' in code
    assert "custom_code" in code


def test_build_code_empty_tables() -> None:
    """No constraints yields empty-table source that compiles (non-list rows too)."""
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
# Persist-and-register helpers
# --------------------------------------------------------------------------- #
def _patch_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace template writes with a no-op."""
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)


def _patch_register(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Replace module loading with a namespace exposing the register function."""

    def _fake_load(file_path: Path) -> Any:
        name = f"src.templates.{file_path.stem}"
        register_name = file_path.stem.replace("custom_", "register_custom_")
        return SimpleNamespace(**{register_name: lambda: calls.append(name)})

    monkeypatch.setattr(app_module, "_load_custom_template_module", _fake_load)


def test_create_custom_template_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """_create_custom_template returns 200 and the key on success."""
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
    """A name that cannot form an identifier returns 400."""
    status, payload = app_module._create_custom_template(
        name="!!!",
        language="zh",
        lines=1,
        syllables_per_line=[2],
        alternatives=[[]],
        custom_code="",
    )
    assert status == 400
    assert "Template name" in payload["message"]


def test_create_custom_template_bad_rhyme_scheme() -> None:
    """The persist helper validates rhyme scheme; a length mismatch returns 400."""
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
    assert "Rhyme scheme" in payload["message"]


def test_create_custom_template_write_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed write returns 500."""

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
    assert "Failed to write template file" in payload["message"]


def test_create_custom_template_register_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration failure returns 500."""
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
    assert "Template registration failed" in payload["message"]


def test_create_custom_template_from_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """An AI draft can be persisted and registered directly."""
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
# Create-template route: new fields
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Unified conversion API
# --------------------------------------------------------------------------- #
def test_convert_requires_csrf(client: FlaskClient) -> None:
    """The conversion endpoint requires a CSRF token."""
    assert client.post("/api/templates/convert", json={}).status_code == 403


def test_convert_not_dict(client: FlaskClient) -> None:
    """A non-object request body returns 400."""
    resp = client.post("/api/templates/convert", data="x", headers=_csrf_headers())
    assert resp.status_code == 400


def test_convert_missing_base_key(client: FlaskClient) -> None:
    """A missing source-template key returns 400."""
    resp = client.post(
        "/api/templates/convert", json={"language": "en"}, headers=_csrf_headers()
    )
    assert resp.status_code == 400
    assert "source template" in resp.get_json()["message"]


def test_convert_unknown_key(client: FlaskClient) -> None:
    """An unknown source template returns 400."""
    resp = client.post(
        "/api/templates/convert",
        json={"base_template_key": "nope", "language": "en"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_convert_bad_language(client: FlaskClient) -> None:
    """An unknown target language returns 400."""
    resp = client.post(
        "/api/templates/convert",
        json={"base_template_key": "en_sonnet", "language": "xx"},
        headers=_csrf_headers(),
    )
    assert resp.status_code == 400


def test_convert_bad_mapping(client: FlaskClient) -> None:
    """An invalid mapping returns 400."""
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
    """Success: constraints are mapped and rhyme scheme plus code are copied."""
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
    assert data["source_name"] == "Joy of Meeting"
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
    """Converting a custom template also copies its custom code (temp registry)."""
    from src.templates import PoetryTemplate, _registry, register

    class _WithCode(PoetryTemplate):
        """Temporary template with custom code."""

        name = "带代码模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        rhyme_scheme = "A"
        custom_code = "errors.append('x')"

        def get_syllable_constraints(self) -> Any:
            """Per-position constraints."""
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
    """Convert a quatrain: structural rules ride along with mapped values."""
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
    assert "Rules:" in data["rule_note"]
    assert "rule_note" in data["carried_rules"]


def _structural_rules() -> dict[str, Any]:
    """Build valid data-driven regulated-verse structural rules."""
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
    """Structural-rule source imports check_jinti_rules and skips generic rhyme."""
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
    """The rule description is written to the rule_note class attribute."""
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
    """The create route accepts a rule note and rejects overlong ones with 400."""
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
    """The conversion endpoint copies the rule note and reports it as carried."""
    from src.templates import PoetryTemplate, _registry, register

    class _Note(PoetryTemplate):
        """Temporary template with a rule description."""

        name = "带描述来源"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "注意对仗"

        def get_syllable_constraints(self) -> Any:
            """A free constraint table."""
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
    """Structural-rule templates persist and register (writes and load mocked)."""
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
    """Invalid structural rules return 400."""
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
    assert "structural rule" in payload["message"]


def test_route_create_with_structural_rules(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The create-template route accepts and validates structural_rules."""
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
    """Structural rules from an AI draft are written into the generated source."""
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
# Source-template code extraction / AI rewrite options
# --------------------------------------------------------------------------- #
def test_template_source_code_builtin() -> None:
    """Built-in template source includes the class and its rule helpers."""
    from src.templates import get

    code = app_module._template_source_code("zh_wujue", get("zh_wujue"))
    assert "class WujueTemplate" in code
    assert "_check_jinti_full" in code
    assert "_TONGYUN = " in code


def test_template_source_code_builtin_inspect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return an empty string when the class source cannot be read."""
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
    """Custom templates read the persisted source first."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """Test template."""

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
    """Fall back to rebuilding from the spec when source reading fails."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """Test template."""

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
    """Skip a helper whose source cannot be read (class source is kept)."""
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
    """Rebuild source from the template spec when the source file is missing."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """Test template."""

        name = "重建模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

        def get_syllable_constraints(self) -> Any:
            """A constraint table."""
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
    """Return an empty string when rebuilding raises (AI rewrite degrades)."""
    from src.templates import PoetryTemplate, _registry, register

    class _Tpl(PoetryTemplate):
        """Test template whose to_dict fails."""

        name = "坏模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

        def to_dict(self) -> dict[str, Any]:
            """Always raises."""
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
    """Replace TemplateCodeRewriter and record its call arguments."""
    record: dict[str, Any] = {}
    fake_class: Any

    if isinstance(result, Exception):

        class fake_class:  # type: ignore[no-redef]
            """Stub that raises."""

            def __init__(self, config: dict[str, Any]) -> None:
                record["config"] = config

            def rewrite(self, **kwargs: Any) -> dict[str, Any]:
                record["kwargs"] = kwargs
                raise result

    else:

        class fake_class:  # type: ignore[no-redef]
            """Stub that returns a preset result."""

            def __init__(self, config: dict[str, Any]) -> None:
                record["config"] = config

            def rewrite(self, **kwargs: Any) -> dict[str, Any]:
                record["kwargs"] = kwargs
                return dict(result)

    monkeypatch.setattr("src.agents.editor_ai.TemplateCodeRewriter", fake_class)
    return record


def _editor_config(api_key: str = "k") -> SimpleNamespace:
    """Build a template-AI config."""
    return SimpleNamespace(
        editor={"base_url": "http://x", "api_key": api_key, "model": "m"}
    )


def test_convert_with_ai_rewrite_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With AI rewrite enabled, returned code replaces the deterministic code."""
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
    """With no template AI configured, degrade and report an error message."""
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
    assert "not configured" in data["ai_rewrite_error"]


def test_convert_with_ai_rewrite_source_unavailable(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade with a hint when the source code cannot be extracted."""
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
    assert "Unable to get source template code" in resp.get_json()["ai_rewrite_error"]


def test_convert_with_ai_rewrite_error_and_exception(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade with a hint when the AI returns an error or raises."""
    monkeypatch.setattr("src.config.get_config", lambda: _editor_config())
    monkeypatch.setattr(app_module, "_template_source_code", lambda key, tpl: "SOURCE")
    _patch_ai_rewriter(monkeypatch, {"status": "error", "message": "AI rewrite failed"})
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
    assert "AI rewrite failed" in resp.get_json()["ai_rewrite_error"]

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
    assert "Template code AI rewrite failed" in resp.get_json()["ai_rewrite_error"]


def test_route_create_with_alternatives_and_rhyme(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route accepts alternatives / rhyme_scheme / rhyme_distinct."""
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
    """A rhyme-scheme length mismatch returns 400."""
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
    assert "Rhyme scheme" in resp.get_json()["message"]


def test_route_create_alternatives_with_non_list_entries(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-list entries in alternatives are tolerated as empty tables."""
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
# Edit-template socket
# --------------------------------------------------------------------------- #
def test_edit_template_requires_prompt() -> None:
    """An empty prompt returns an error directly."""
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": " ", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"


def test_edit_template_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return an error when the template AI has no API key."""
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(editor={"base_url": "u", "api_key": "", "model": "m"}),
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"
    assert "API key" in done["args"][0]["message"]


def _patch_editor_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the config with an editor endpoint that has an API key."""
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(editor={"base_url": "u", "api_key": "k", "model": "m"}),
    )


def _fake_editor(
    *, submitted: bool, message: str = "Done", fail: bool = False
) -> type[Any]:
    """Build a fake template-editing AI class."""

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
                emit({"type": "message", "content": "Okay"})
            draft = TemplateDraft(name="AI模板", language="zh", lines=1)
            draft.syllables_per_line = [2]
            draft.alternatives = [[["平", ""]]]
            return editor_ai.EditorResult(draft, submitted, message)

    return _Fake


def test_edit_template_applies_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the AI does not submit, return the draft for the UI (with events)."""
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
    """After the AI submits, the server creates the template and returns created_key."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(editor_ai, "TemplateEditorAI", _fake_editor(submitted=True))
    monkeypatch.setattr(
        app_module,
        "_create_custom_template_from_draft",
        lambda draft: (200, {"key": "custom_ai", "message": "Created"}),
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
    """Return an error when creation after an AI submit fails."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(editor_ai, "TemplateEditorAI", _fake_editor(submitted=True))
    monkeypatch.setattr(
        app_module,
        "_create_custom_template_from_draft",
        lambda draft: (500, {"message": "Template registration failed: boom"}),
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    payload = done["args"][0]
    assert payload["status"] == "error"
    assert "Template registration failed" in payload["message"]


def test_edit_template_agent_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return an error event when the AI agent raises."""
    _patch_editor_config(monkeypatch)
    monkeypatch.setattr(
        editor_ai, "TemplateEditorAI", _fake_editor(submitted=False, fail=True)
    )
    sio = _sio_client()
    sio.emit("edit_template", {"prompt": "建一个模板", "draft": {}})
    done = _wait_event(sio, "template_ai_done")
    assert done["args"][0]["status"] == "error"
    assert "processing failed" in done["args"][0]["message"]
