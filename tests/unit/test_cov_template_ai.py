# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""模板编辑 AI 相关新增模块的单元测试.

覆盖：配置 editor 端点、模板描述的多约束支持、MeterValidator 多约束分支、
通用押韵模块、模板工具、模板编辑 AI 代理。
"""

from pathlib import Path
from typing import Any, ClassVar

import pytest

from src import config as config_module
from src.agents import editor_ai
from src.agents.editor_ai import EditorResult, TemplateEditorAI
from src.models.syllable import Syllable
from src.prosody.meter_validator import MeterValidator
from src.templates import (
    PoetryTemplate,
    _describe_constraint_table,
    describe_template_from_dict,
)
from src.templates import rhyme as rhyme_mod
from src.templates.convert import normalize_constraint_value
from src.tools import template_tools as tools
from tests.helpers import StubLLMClient, make_stub, tool_call


def _syl() -> dict[str, Any]:
    """构造空约束单元格."""
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": {"tone": "", "stress": "", "length": ""},
    }


def _zh(tone: str) -> dict[str, Any]:
    """构造中文平仄约束单元格."""
    cell = _syl()
    cell["attributes"]["tone"] = tone
    return cell


def _empty_syl() -> Syllable:
    """构造空音节."""
    return Syllable(
        onset="",
        nucleus="",
        coda="",
        attributes={"tone": "", "stress": "", "length": ""},
    )


# --------------------------------------------------------------------------- #
# 配置 editor 端点
# --------------------------------------------------------------------------- #
def test_config_editor_defaults_and_setter(tmp_path: Path) -> None:
    """Editor 缺省回退默认值，setter 写入配置数据."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    assert cfg.editor["model"] == config_module.DEFAULT_EDITOR["model"]
    cfg.editor = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["editor"]["model"] == "m"
    assert cfg.editor["api_key"] == "k"


def test_config_editor_non_dict_falls_back(tmp_path: Path) -> None:
    """Editor 字段非 dict 时回退默认值."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"editor": [1, 2]}
    cfg._loaded = True
    assert cfg.editor["model"] == config_module.DEFAULT_EDITOR["model"]


# --------------------------------------------------------------------------- #
# 模板描述：多约束与基类方法
# --------------------------------------------------------------------------- #
class _AltTemplate(PoetryTemplate):
    """用于测试多约束序列化/描述的模板."""

    name = "多约束"
    language = "zh"
    lines = 2
    syllables_per_line: ClassVar[list[int]] = [2, 2]

    def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
        """返回第一份约束."""
        return [[_zh("平"), _syl()], [_zh("仄"), _syl()]]

    def get_syllable_constraint_alternatives(self) -> list[list[list[dict[str, Any]]]]:
        """返回两份约束."""
        return [
            self.get_syllable_constraints(),
            [[_zh("仄"), _syl()], [_syl(), _syl()]],
        ]


class _BareAlt(PoetryTemplate):
    """未覆写多约束方法的模板."""

    name = "bare"
    language = "zh"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [1]


def test_base_alternatives_default_none() -> None:
    """基类默认无多约束."""
    assert _BareAlt().get_syllable_constraint_alternatives() is None


def test_describe_dict_with_alternatives() -> None:
    """describe_template_from_dict 支持多份约束（含空表容错）."""
    desc = describe_template_from_dict(
        {
            "lines": 2,
            "syllables_per_line": [2, 2],
            "syllable_constraint_alternatives": [
                [[_zh("平")], []],
                None,
            ],
        }
    )
    assert "2 种音节约束" in desc
    assert "约束种类 1" in desc
    assert "约束种类 2" in desc
    assert "tone=平" in desc


def test_describe_dict_single_table() -> None:
    """无多约束时沿用单表描述."""
    desc = describe_template_from_dict(
        {
            "lines": 1,
            "syllables_per_line": [1],
            "syllable_constraints": [[_zh("仄")]],
        }
    )
    assert "tone=仄" in desc
    assert "约束种类" not in desc


def test_alt_template_to_dict_and_describe() -> None:
    """多约束模板 to_dict/describe 包含 alternatives."""
    tpl = _AltTemplate()
    data = tpl.to_dict()
    assert data["syllable_constraints"] is not None
    assert len(data["syllable_constraint_alternatives"]) == 2
    assert "2 种音节约束" in tpl.describe()


def test_describe_constraint_table_skips_non_dict_cells() -> None:
    """_describe_constraint_table 容错非 dict 单元格."""
    desc = _describe_constraint_table([1], [[_syl(), _syl()]])
    assert "第1行" in desc


# --------------------------------------------------------------------------- #
# MeterValidator：多约束（或关系）
# --------------------------------------------------------------------------- #
def _alt_template_dict(
    alternatives: list[list[list[dict[str, Any]]]],
) -> dict[str, Any]:
    """构造带多约束的模板字典."""
    return {
        "name": "多约束测试",
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [2, 2],
        "syllable_constraints": alternatives[0],
        "syllable_constraint_alternatives": alternatives,
    }


def test_validator_alternatives_second_matches() -> None:
    """第一份约束不满足、第二份满足时通过."""
    alternatives = [
        [[_zh("仄"), _syl()], [_zh("平"), _syl()]],
        [[_zh("平"), _syl()], [_zh("仄"), _syl()]],
    ]
    result = MeterValidator().validate(
        ["山风", "月雪"], _alt_template_dict(alternatives)
    )
    assert result.passed, result.errors


def test_validator_alternatives_none_match_reports_best() -> None:
    """所有约束都不满足时返回错误最少的一份错误."""
    alternatives = [
        [[_zh("仄"), _syl()], [_zh("平"), _syl()]],
        [[_zh("仄"), _zh("仄")], [_zh("平"), _syl()]],
    ]
    result = MeterValidator().validate(
        ["山风", "月雪"], _alt_template_dict(alternatives)
    )
    assert not result.passed
    assert result.errors


def test_validator_alternatives_empty_variants() -> None:
    """某行无音节时多约束检查报告无音节."""
    alternatives = [[[_zh("平")], [_zh("平")]]]
    result = MeterValidator().validate(["abc", "abc"], _alt_template_dict(alternatives))
    assert not result.passed
    assert any("无音节" in e for e in result.errors)


def test_validator_alternatives_none_when_missing() -> None:
    """无 alternatives 键时返回空列表（覆盖早期返回）."""
    assert MeterValidator()._constraint_alternatives({}) == []


def test_validate_line_alternatives_match_second() -> None:
    """单行校验：第二份约束满足即通过."""
    alternatives = [
        [[_zh("仄"), _syl()], [_syl(), _syl()]],
        [[_zh("平"), _syl()], [_syl(), _syl()]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_no_match() -> None:
    """单行校验：所有约束都不满足时给出错误."""
    alternatives = [
        [[_zh("平"), _zh("仄")], [_syl(), _syl()]],
        [[_zh("仄"), _zh("平")], [_syl(), _syl()]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert not result.passed
    assert result.errors


def test_validate_line_alternatives_short_table_is_free() -> None:
    """单行校验：某份约束表短于行号时该份视为无约束（通过）."""
    alternatives = [
        [[_zh("仄")]],
        [[_zh("平")]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 1, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_empty_line_constraints() -> None:
    """单行校验：某份约束该行为空表时视为无约束（通过）."""
    alternatives = [
        [[], [_zh("仄")]],
        [[_zh("仄")], []],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_empty_variants() -> None:
    """单行校验：行无音节时多约束不报逐位错误."""
    alternatives = [[[_zh("平")], [_zh("平")]]]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("abc", 0, template)
    assert not result.passed
    assert len(result.errors) == 1


# --------------------------------------------------------------------------- #
# 通用押韵模块
# --------------------------------------------------------------------------- #
def test_last_word_variants() -> None:
    """行末词提取：有词/空行."""
    assert rhyme_mod._last_word("The quick brown fox") == "fox"
    assert rhyme_mod._last_word("") == ""
    assert rhyme_mod._last_word("don't stop") == "stop"


def test_syllable_rhyme_key_empty() -> None:
    """通用音节韵脚 key：空韵腹韵尾返回空串."""
    assert rhyme_mod._syllable_rhyme_key(_empty_syl()) == ""
    assert (
        rhyme_mod._syllable_rhyme_key(
            Syllable(onset="", nucleus="a", coda="n", attributes={})
        )
        == "an"
    )


def test_rhyme_keys_english() -> None:
    """英语按重读音节尾串生成韵脚 key；空行返回 None."""
    keys = rhyme_mod.rhyme_keys("en", "a light")
    assert keys is not None
    assert all(k.startswith("en:") for k in keys)
    assert rhyme_mod.rhyme_keys("en", "!!!") is None


def test_rhyme_keys_french() -> None:
    """法语按词末元音核生成韵脚 key；空行返回 None."""
    keys = rhyme_mod.rhyme_keys("fr", "il parle")
    assert keys is not None
    assert all(k.startswith("fr:") for k in keys)
    assert rhyme_mod.rhyme_keys("fr", "!!!") is None


def test_rhyme_keys_zh_with_and_without_syllables() -> None:
    """中文押韵 key 使用传入音节或自行分析；空行返回 None."""
    keys = rhyme_mod.rhyme_keys("zh", "风")
    assert keys is not None and keys == {"zh:庚"}
    provided = [Syllable(onset="d", nucleus="e", coda="ng", attributes={})]
    assert rhyme_mod.rhyme_keys("zh", "灯", provided) == {"zh:庚"}
    assert rhyme_mod.rhyme_keys("zh", "") is None
    assert rhyme_mod.rhyme_keys("zh", "风", [_empty_syl()]) is None


def test_rhyme_keys_generic_language() -> None:
    """其他语言使用韵腹+韵尾；无音节返回 None."""
    provided = [Syllable(onset="c", nucleus="a", coda="", attributes={})]
    assert rhyme_mod.rhyme_keys("it", "casa", provided) == {"it:a"}
    assert rhyme_mod.rhyme_keys("it", "") is None
    assert rhyme_mod.rhyme_keys("it", "casa", [_empty_syl()]) is None


def test_parse_rhyme_scheme() -> None:
    """韵式解析支持分隔符与不押韵标记."""
    assert rhyme_mod.parse_rhyme_scheme("ABAB CDCD") == [
        "A",
        "B",
        "A",
        "B",
        "C",
        "D",
        "C",
        "D",
    ]
    assert rhyme_mod.parse_rhyme_scheme("AB--") == ["A", "B", None, None]
    assert rhyme_mod.parse_rhyme_scheme("") == []


def test_normalize_rhyme_scheme_branches() -> None:
    """韵式校验：空、非法字符、长度不符、合法."""
    assert rhyme_mod.normalize_rhyme_scheme("", 4) == ("", None)
    scheme, error = rhyme_mod.normalize_rhyme_scheme("A-B1", 3)
    assert scheme == "" and error is not None and "非法字符" in error
    scheme, error = rhyme_mod.normalize_rhyme_scheme("AB", 4)
    assert scheme == "" and error is not None and "长度" in error
    assert rhyme_mod.normalize_rhyme_scheme("ABAB CDCD", 8) == ("ABABCDCD", None)


def test_check_rhyme_scheme_empty_and_too_long() -> None:
    """空韵式不检查；韵式长于诗稿时报错."""
    assert rhyme_mod.check_rhyme_scheme("zh", ["春江"], "") == []
    errors = rhyme_mod.check_rhyme_scheme("zh", ["春江"], "AB")
    assert any("超过诗稿行数" in e for e in errors)


def test_check_rhyme_scheme_pass_and_mismatch() -> None:
    """同韵组共享韵脚通过，不同韵脚报错."""
    good = ["春江花月风", "野渡无人灯"]
    assert rhyme_mod.check_rhyme_scheme("zh", good, "AA") == []
    bad = ["春江花月风", "野渡无人空"]
    errors = rhyme_mod.check_rhyme_scheme("zh", bad, "AA")
    assert any("不匹配" in e for e in errors)


def test_check_rhyme_scheme_unable_line_and_single_group() -> None:
    """无法确定韵脚的行报错；单行韵组跳过检查."""
    errors = rhyme_mod.check_rhyme_scheme("en", ["!!!", "???"], "AA")
    assert any("无法确定韵脚" in e for e in errors)
    assert rhyme_mod.check_rhyme_scheme("zh", ["春江花月风"], "A") == []


def test_check_rhyme_scheme_no_rhyme_marker() -> None:
    """韵式中的 '-' 行不参与押韵检查."""
    poem = ["春江花月风", "-", "野渡无人灯"]
    assert rhyme_mod.check_rhyme_scheme("zh", poem, "A-A") == []


def test_check_rhyme_scheme_distinct() -> None:
    """不同韵组互异：共享韵脚报错，不共享通过."""
    poem = ["a light", "a night", "a night", "a light"]
    errors = rhyme_mod.check_rhyme_scheme("en", poem, "ABAB", distinct=True)
    assert any("互不相同" in e for e in errors)
    poem2 = ["a light", "a day", "a night", "the day"]
    assert rhyme_mod.check_rhyme_scheme("en", poem2, "ABAB", distinct=True) == []


def test_rhyme_scheme_description() -> None:
    """韵式描述：空串返回空，非空按每 4 行分组."""
    assert rhyme_mod.rhyme_scheme_description("") == ""
    assert "ABAB CDCD" in rhyme_mod.rhyme_scheme_description("abab cdcd")


# --------------------------------------------------------------------------- #
# 模板工具：草稿规整与工具执行
# --------------------------------------------------------------------------- #
def test_draft_normalize_fixes_invalid_fields() -> None:
    """草稿规整：非法语言/行数/音节数/约束值被修正."""
    draft = tools.TemplateDraft()
    draft.language = "xx"
    draft.lines = "oops"  # type: ignore[assignment]
    draft.syllables_per_line = [0, "a"]  # type: ignore[list-item]
    draft.alternatives = []
    draft.normalize()
    assert draft.language == "zh"
    assert len(draft.syllables_per_line) == draft.lines
    assert all(v >= 1 for v in draft.syllables_per_line)
    assert len(draft.alternatives) == 1


def test_draft_normalize_pads_and_truncates() -> None:
    """草稿规整：补齐缺失约束单元格、截断多余约束种类."""
    draft = tools.TemplateDraft()
    draft.lines = 2
    draft.syllables_per_line = [3, 2]
    draft.alternatives = [
        [["平"], ["仄", "bad", "bad", "bad"]],
        [["平", "平"], ["仄"]],
        [["平", "平"], ["仄"]],
        [["平", "平"], ["仄"]],
        [],
    ]
    draft.normalize()
    assert len(draft.alternatives) == 5
    assert draft.alternatives[0][0] == ["平", "", ""]
    assert draft.alternatives[0][1] == ["仄", ""]


def test_draft_to_payload_and_constraint_tables() -> None:
    """草稿序列化与约束表转换（zh 与 fr）."""
    draft = tools.TemplateDraft(name="x")
    draft.language = "zh"
    draft.lines = 1
    draft.syllables_per_line = [2]
    draft.alternatives = [[["平", ""]]]
    payload = draft.to_payload()
    assert payload["name"] == "x"
    assert payload["alternatives"] == [[["平", ""]]]
    table = draft.constraint_tables()[0]
    assert table[0][0]["attributes"]["tone"] == "平"
    assert table[0][1]["attributes"]["tone"] == ""

    draft.language = "fr"
    draft.normalize()
    assert draft.constraint_tables()[0][0][0]["attributes"]["tone"] == ""


def test_draft_from_payload_tolerant() -> None:
    """从前端草稿构造时容错非法字段."""
    draft = tools.draft_from_payload(
        {
            "name": " n ",
            "language": "en",
            "lines": "bad",
            "syllables_per_line": "bad",
            "alternatives": [["bad-row"], [["light", ""]], "bad-alt"],
            "rhyme_scheme": "AA",
            "rhyme_distinct": True,
            "code": "x = 1",
        }
    )
    assert draft.name == "n"
    assert draft.lines == 4
    assert draft.rhyme_distinct is True
    assert draft.code == "x = 1"
    assert draft.alternatives
    assert len(tools.draft_from_payload({}).alternatives) == 1


def test_normalize_constraint_value() -> None:
    """约束值归一化：空、别名、非法、无维度语言."""
    assert normalize_constraint_value("zh", "") == ""
    assert normalize_constraint_value("zh", "平") == "平"
    assert normalize_constraint_value("en", "重") == "heavy"
    assert normalize_constraint_value("la", "短") == "short"
    assert normalize_constraint_value("en", "??") is None
    assert normalize_constraint_value("fr", "平") == ""


def test_execute_set_template_info() -> None:
    """设置模板信息：名称/语言/行数与错误分支."""
    draft = tools.TemplateDraft()
    assert "error" in tools.execute_set_template_info(draft, {"name": " "})
    assert "error" in tools.execute_set_template_info(draft, {"language": "xx"})
    result = tools.execute_set_template_info(
        draft, {"name": "新模板", "language": "en", "lines": 5}
    )
    assert result["status"] == "ok"
    assert draft.name == "新模板" and draft.language == "en" and draft.lines == 5


def test_execute_set_syllables() -> None:
    """设置每行音节数：错误分支与成功."""
    draft = tools.TemplateDraft()
    draft.lines = 2
    draft.normalize()
    assert "error" in tools.execute_set_syllables(draft, {"syllables": "x"})
    assert "error" in tools.execute_set_syllables(draft, {"syllables": [3]})
    assert "error" in tools.execute_set_syllables(draft, {"syllables": ["a", 3]})
    assert "error" in tools.execute_set_syllables(draft, {"syllables": [0, 3]})
    result = tools.execute_set_syllables(draft, {"syllables": [3, 4]})
    assert result["status"] == "ok"
    assert draft.syllables_per_line == [3, 4]


def test_execute_set_kind_count() -> None:
    """设置约束种类：非法值、扩容、缩容."""
    draft = tools.TemplateDraft()
    assert "error" in tools.execute_set_kind_count(draft, {"count": "x"})
    assert "error" in tools.execute_set_kind_count(draft, {"count": 0})
    assert "error" in tools.execute_set_kind_count(draft, {"count": 99})
    tools.execute_set_kind_count(draft, {"count": 3})
    assert len(draft.alternatives) == 3
    tools.execute_set_kind_count(draft, {"count": 1})
    assert len(draft.alternatives) == 1


def test_execute_set_constraints() -> None:
    """填写约束：错误分支与成功（含越界/非法值/非列表行）."""
    draft = tools.TemplateDraft()
    draft.lines = 2
    draft.syllables_per_line = [2, 2]
    draft.normalize()
    assert "error" in tools.execute_set_constraints(draft, {"constraints": "x"})
    assert "error" in tools.execute_set_constraints(
        draft, {"constraints": [["平"]], "alternative": "x"}
    )
    assert "error" in tools.execute_set_constraints(
        draft, {"constraints": [["平"]], "alternative": 5}
    )
    assert "error" in tools.execute_set_constraints(
        draft, {"constraints": [["平", "??"], []]}
    )
    result = tools.execute_set_constraints(draft, {"constraints": [["平"], "bad-row"]})
    assert result["status"] == "ok"
    assert draft.alternatives[0][0] == ["平", ""]
    assert draft.alternatives[0][1] == ["", ""]


def test_execute_set_rhyme_and_code() -> None:
    """设置韵式与自定义代码."""
    draft = tools.TemplateDraft()
    draft.lines = 4
    draft.normalize()
    assert "error" in tools.execute_set_rhyme(draft, {"scheme": "AB"})
    result = tools.execute_set_rhyme(draft, {"scheme": "abab", "distinct": True})
    assert result["status"] == "ok"
    assert draft.rhyme_scheme == "ABAB" and draft.rhyme_distinct is True
    tools.execute_set_rhyme(draft, {"scheme": ""})
    assert draft.rhyme_scheme == ""
    tools.execute_set_code(draft, {"code": "a\r\nb"})
    assert draft.code == "a\nb"


def test_draft_from_payload_accepts_syllables() -> None:
    """从前端草稿构造时接受每行音节数组."""
    draft = tools.draft_from_payload(
        {"language": "zh", "lines": 2, "syllables_per_line": [3, 4]}
    )
    assert draft.syllables_per_line == [3, 4]


def test_execute_set_from_template_converts() -> None:
    """从中文模板转化为英语：复制行数/音节数并按映射转换属性值."""
    draft = tools.TemplateDraft(language="en", lines=1)
    draft.normalize()
    result = tools.execute_set_from_template(
        draft,
        {
            "template_key": "zh_xiangjianhuan",
            "mapping": {"平": "heavy", "仄": "light"},
        },
    )
    assert result["status"] == "ok"
    assert draft.lines == 7
    assert result["source_language"] == "zh"
    # 押韵韵式随模板一起转化/复制。
    assert draft.rhyme_scheme == "AAABBAA"
    values = {
        value for table in draft.alternatives for row in table for value in row if value
    }
    assert values <= {"heavy", "light"}
    assert values


def test_execute_set_from_template_auto_fallback_value() -> None:
    """未配置映射时源值退化处理：目标值保持自由，但行数/音节数仍复制."""
    draft = tools.TemplateDraft(language="en", lines=1)
    draft.normalize()
    result = tools.execute_set_from_template(
        draft, {"template_key": "zh_xiangjianhuan"}
    )
    assert result["status"] == "ok"
    assert draft.lines == 7
    assert all(
        value == "" for table in draft.alternatives for row in table for value in row
    )


def test_execute_set_from_template_interval_and_free() -> None:
    """区间音节数取中点；源模板无逐位约束时全部自由."""
    draft = tools.TemplateDraft(language="zh", lines=1)
    draft.normalize()
    result = tools.execute_set_from_template(draft, {"template_key": "fr_rondeau"})
    assert result["status"] == "ok"
    assert draft.lines == 15
    assert draft.syllables_per_line == [9] * 15
    assert all(
        value == "" for table in draft.alternatives for row in table for value in row
    )


def test_execute_set_from_template_errors() -> None:
    """未知模板 / 空 key / 非法映射值均报错."""
    draft = tools.TemplateDraft()
    draft.normalize()
    assert "error" in tools.execute_set_from_template(draft, {"template_key": ""})
    assert "error" in tools.execute_set_from_template(draft, {"template_key": "nope"})
    assert "error" in tools.execute_set_from_template(
        draft, {"template_key": "zh_xiangjianhuan", "mapping": {"??": "light"}}
    )
    assert "error" in tools.execute_set_from_template(
        draft, {"template_key": "zh_xiangjianhuan", "mapping": {"平": "??"}}
    )


def test_execute_set_from_template_via_dispatch() -> None:
    """set_from_template 可通过统一分发表调用."""
    draft = tools.TemplateDraft(language="en", lines=1)
    draft.normalize()
    result = tools.execute_template_tool(
        draft, "set_from_template", {"template_key": "zh_xiangjianhuan"}
    )
    assert result["status"] == "ok"


def test_convert_syllable_count_branches() -> None:
    """区间/非法值的音节数转换分支."""
    from src.templates.convert import convert_syllable_count

    assert convert_syllable_count(5) == 5
    assert convert_syllable_count((8, 10)) == 9
    assert convert_syllable_count(("a", "b")) == 7
    assert convert_syllable_count("bad") == 7


def test_set_from_template_tolerates_odd_tables() -> None:
    """源模板音节数不足/约束表异常/属性非字典时仍能转化."""
    from src.templates import PoetryTemplate, _registry, register

    class _Dummy(PoetryTemplate):
        """异常结构模板（用于覆盖容错分支）."""

        name = "异常结构"
        language = "fr"
        lines = 2
        syllables_per_line: ClassVar[list[int]] = [2]

        def get_syllable_constraints(self) -> Any:
            """返回非标准约束表."""
            return [
                [{"attributes": "bad"}, {"attributes": {"length": "long"}}],
                "not-a-list",
            ]

    register("test_odd_table", _Dummy())
    try:
        draft = tools.TemplateDraft(language="zh", lines=1)
        draft.normalize()
        result = tools.execute_set_from_template(
            draft, {"template_key": "test_odd_table", "mapping": {"long": "平"}}
        )
        assert result["status"] == "ok"
        assert draft.syllables_per_line == [2, 2]
        assert draft.alternatives[0][1] == ["", ""]
    finally:
        _registry.pop("test_odd_table", None)


def test_execute_set_rule_description() -> None:
    """AI 工具可设置/清除模板规则描述（将作为写作 AI prompt）."""
    draft = tools.TemplateDraft()
    result = tools.execute_template_tool(
        draft,
        "set_rule_description",
        {"description": " 上下联需对仗，意境清远。 "},
    )
    assert result["status"] == "ok"
    assert result["has_rule_note"] is True
    assert draft.rule_note == "上下联需对仗，意境清远。"
    cleared = tools.execute_template_tool(
        draft, "set_rule_description", {"description": ""}
    )
    assert cleared["has_rule_note"] is False
    assert draft.rule_note == ""


def test_draft_rule_note_roundtrip() -> None:
    """草稿载荷包含规则描述，且长度受限."""
    draft = tools.draft_from_payload({"rule_note": "规则描述"})
    assert draft.to_payload()["rule_note"] == "规则描述"
    long_draft = tools.draft_from_payload({"rule_note": "x" * 5000})
    long_draft.normalize()
    assert len(long_draft.rule_note) == 4000


def test_set_from_template_carries_rule_note() -> None:
    """AI 转化时规则描述随草稿携带."""

    class _WithNote(PoetryTemplate):
        """带规则描述的测试模板."""

        name = "带描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "注意对仗"

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """一份自由约束."""
            return [[_syl()]]

    from src.templates import _registry, register

    register("test_tools_note", _WithNote())
    try:
        draft = tools.TemplateDraft(language="en", lines=1)
        draft.normalize()
        result = tools.execute_set_from_template(
            draft, {"template_key": "test_tools_note"}
        )
        assert result["status"] == "ok"
        assert draft.rule_note == "注意对仗"
        assert "rule_note" in result["carried_rules"]
    finally:
        _registry.pop("test_tools_note", None)


def test_draft_structural_rules_roundtrip() -> None:
    """草稿载荷可携带结构规则；非法结构规则被丢弃."""
    rules = {
        "kind": "jinti",
        "attribute": "stress",
        "level_value": "heavy",
        "oblique_value": "light",
        "positions": [1, 3],
        "rhyme_lines": [1, 3],
    }
    draft = tools.draft_from_payload(
        {"language": "en", "lines": 4, "alternatives": [], "structural_rules": rules}
    )
    assert draft.structural_rules is not None
    payload = draft.to_payload()
    assert payload["structural_rules"]["attribute"] == "stress"
    bad = tools.draft_from_payload({"structural_rules": {"kind": "bad"}})
    assert bad.structural_rules is None


def test_set_from_template_carries_structural_rules() -> None:
    """AI 转化绝句时结构规则随草稿携带（不再丢失三平尾/孤平）."""
    draft = tools.TemplateDraft(language="en", lines=1)
    draft.normalize()
    result = tools.execute_set_from_template(
        draft,
        {"template_key": "zh_wujue", "mapping": {"平": "heavy", "仄": "light"}},
    )
    assert result["status"] == "ok"
    assert draft.structural_rules is not None
    assert draft.structural_rules["attribute"] == "stress"
    assert draft.structural_rules["level_value"] == "heavy"
    assert "jinti" in result["carried_rules"]
    assert result["dropped_rules"] == []
    assert result["has_structural_rules"] is True


def test_execute_template_tool_all_dispatch() -> None:
    """全部工具分发分支均可执行."""
    draft = tools.TemplateDraft()
    draft.lines = 1
    draft.normalize()
    assert (
        tools.execute_template_tool(
            draft, "set_syllables_per_line", {"syllables": [2]}
        )["status"]
        == "ok"
    )
    assert (
        tools.execute_template_tool(draft, "set_constraint_kind_count", {"count": 2})[
            "status"
        ]
        == "ok"
    )
    assert (
        tools.execute_template_tool(
            draft, "set_syllable_constraints", {"constraints": [["平", "仄"]]}
        )["status"]
        == "ok"
    )
    assert (
        tools.execute_template_tool(draft, "set_rhyme_scheme", {"scheme": "A"})[
            "status"
        ]
        == "ok"
    )
    assert (
        tools.execute_template_tool(draft, "set_custom_code", {"code": ""})["status"]
        == "ok"
    )


def test_execute_template_tool_dispatch() -> None:
    """工具分发：读取草稿、未知工具、提交前校验名称."""
    draft = tools.TemplateDraft()
    draft.lines = 1
    draft.normalize()
    result = tools.execute_template_tool(draft, "get_template_draft", {})
    assert result["status"] == "ok" and "draft" in result
    assert "error" in tools.execute_template_tool(draft, "unknown", {})
    assert "error" in tools.execute_template_tool(draft, "submit_template", {})
    draft.name = "x"
    result = tools.execute_template_tool(draft, "submit_template", {})
    assert result["status"] == "submitted"
    assert draft.submitted is True


# --------------------------------------------------------------------------- #
# 模板编辑 AI 代理
# --------------------------------------------------------------------------- #
def _patch_editor_llm(monkeypatch: pytest.MonkeyPatch, stub: type[Any]) -> None:
    """把 editor_ai 的 LLMClient 替换为桩类."""
    monkeypatch.setattr(editor_ai, "LLMClient", stub)


def test_editor_no_tool_with_name_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 直接回答且草稿已有名称时结束（含思考/回答事件）."""
    _patch_editor_llm(
        monkeypatch,
        make_stub(
            chat=[
                {
                    "role": "assistant",
                    "content": "已完成",
                    "tool_calls": [],
                    "reasoning_content": "思考中",
                }
            ]
        ),
    )
    events: list[dict[str, Any]] = []
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {"name": "x"}, emit=events.append)
    assert not result.submitted
    assert result.message == "已完成"
    assert {e["type"] for e in events} == {"thinking", "message"}


def test_editor_reminder_then_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 未调工具且草稿无名称时先提醒，随后调工具完成配置."""
    _patch_editor_llm(
        monkeypatch,
        make_stub(
            chat=[
                {"role": "assistant", "content": "好的", "tool_calls": []},
                tool_call("set_template_info", {"name": "浣溪沙", "lines": 2}),
            ]
        ),
    )
    events: list[dict[str, Any]] = []
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {}, emit=events.append)
    assert result.draft.name == "浣溪沙"
    assert any(e["type"] == "tool" for e in events)
    assert not result.submitted


def test_editor_submit_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 调用 submit_template 时 submitted=True."""
    _patch_editor_llm(
        monkeypatch,
        make_stub(
            chat=[
                tool_call("set_template_info", {"name": "x", "lines": 1}),
                tool_call("submit_template", {}),
            ]
        ),
    )
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {}, emit=None)
    assert result.submitted
    assert result.draft.submitted


def test_editor_llm_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 调用异常时返回错误并推送 error 事件."""
    stub = make_stub()

    class _Boom(stub):  # type: ignore[misc, valid-type]
        def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> Any:
            raise RuntimeError("boom")

    _patch_editor_llm(monkeypatch, _Boom)
    events: list[dict[str, Any]] = []
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {}, emit=events.append)
    assert "失败" in result.message
    assert events[0]["type"] == "error"


def test_editor_max_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """达到最大轮数时停止并推送 info 事件."""
    _patch_editor_llm(
        monkeypatch,
        make_stub(chat=[tool_call("set_template_info", {"name": "x"})]),
    )
    events: list[dict[str, Any]] = []
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {}, emit=events.append, max_rounds=1)
    assert not result.submitted
    assert any(e["type"] == "info" for e in events)


def test_editor_non_dict_tool_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具参数非 dict 时按空字典执行."""
    _patch_editor_llm(
        monkeypatch,
        make_stub(
            chat=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_x",
                            "name": "get_template_draft",
                            "arguments": None,
                        }
                    ],
                },
                tool_call("submit_template", {}),
            ]
        ),
    )
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    events: list[dict[str, Any]] = []
    result = agent.edit("配置", {"name": "x"}, emit=events.append)
    assert result.submitted
    assert any(e["type"] == "tool" for e in events)


def test_format_value_mapping_branches() -> None:
    """属性值映射说明：普通映射 / 空映射 / 目标无属性."""
    text = editor_ai.format_value_mapping("zh", "en", {"平": "heavy", "仄": "light"})
    assert "tone" in text and "stress" in text
    assert "平（平声）→ heavy（重读）" in text
    assert "仄（仄声）→ light（轻读）" in text

    empty = editor_ai.format_value_mapping("zh", "en", {})
    assert "未提供具体属性值映射" in empty

    no_target = editor_ai.format_value_mapping("zh", "fr", {"平": "heavy"})
    assert "目标语言没有逐位音节属性" in no_target

    unknown = editor_ai.format_value_mapping("xx", "yy", {})
    assert "目标语言没有逐位音节属性" in unknown


def test_build_rewrite_system_contains_context() -> None:
    """转写提示包含映射、源代码、目标规格、运行环境与规则描述."""
    text = editor_ai._build_rewrite_system(
        "zh",
        "en",
        {"平": "heavy"},
        "errors.append('x')",
        {"lines": 4, "syllables_per_line": [5, 5, 5, 5], "alternatives": []},
        rule_note="注意对仗",
    )
    assert "平（平声）→ heavy（重读）" in text
    assert "errors.append('x')" in text
    assert "validate_full" in text
    assert "注意对仗" in text
    assert "self.structural_rules" in text


def test_rewriter_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 返回合法代码时转写成功."""
    stub = make_stub(
        chat=[tool_call("submit_code", {"code": "errors.append('x')", "notes": "说明"})]
    )
    monkeypatch.setattr(editor_ai, "LLMClient", stub)
    rewriter = editor_ai.TemplateCodeRewriter(
        {"base_url": "u", "api_key": "k", "model": "m"}
    )
    result = rewriter.rewrite(
        "zh", "en", {"平": "heavy"}, "src", {"lines": 1, "syllables_per_line": [1]}
    )
    assert result["status"] == "ok"
    assert result["code"] == "errors.append('x')"
    assert result["notes"] == "说明"


def test_rewriter_retries_empty_and_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空代码/语法错误时重试，直到拿到合法代码."""
    stub = make_stub(
        chat=[
            tool_call("submit_code", {"code": ""}),
            tool_call("submit_code", {"code": "if True"}),
            tool_call("submit_code", {"code": "errors.append('ok')"}),
        ]
    )
    monkeypatch.setattr(editor_ai, "LLMClient", stub)
    rewriter = editor_ai.TemplateCodeRewriter(
        {"base_url": "u", "api_key": "k", "model": "m"}
    )
    result = rewriter.rewrite(
        "zh",
        "en",
        {},
        "src",
        {"lines": 1, "syllables_per_line": [1]},
        max_rounds=3,
    )
    assert result["status"] == "ok"
    assert result["code"] == "errors.append('ok')"


def test_rewriter_no_tool_calls_then_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 未调用工具时提示后继续，并在下一轮成功."""
    stub = make_stub(
        chat=[
            {"role": "assistant", "content": "代码如下", "tool_calls": []},
            tool_call("submit_code", {"code": "errors.append('y')"}),
        ]
    )
    monkeypatch.setattr(editor_ai, "LLMClient", stub)
    rewriter = editor_ai.TemplateCodeRewriter(
        {"base_url": "u", "api_key": "k", "model": "m"}
    )
    result = rewriter.rewrite(
        "zh", "en", {}, "src", {"lines": 1, "syllables_per_line": [1]}
    )
    assert result["status"] == "ok"


def test_rewriter_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """调用异常 / 始终无合法代码时返回错误."""
    stub = make_stub(chat=[])
    monkeypatch.setattr(editor_ai, "LLMClient", stub)

    class _Boom(stub):  # type: ignore[misc, valid-type]
        def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> Any:
            raise RuntimeError("boom")

    monkeypatch.setattr(editor_ai, "LLMClient", _Boom)
    rewriter = editor_ai.TemplateCodeRewriter(
        {"base_url": "u", "api_key": "k", "model": "m"}
    )
    result = rewriter.rewrite(
        "zh", "en", {}, "src", {"lines": 1, "syllables_per_line": [1]}
    )
    assert result["status"] == "error"
    assert "boom" in result["message"]

    monkeypatch.setattr(
        editor_ai,
        "LLMClient",
        make_stub(chat=[tool_call("submit_code", {"code": "if True"})]),
    )
    rewriter = editor_ai.TemplateCodeRewriter(
        {"base_url": "u", "api_key": "k", "model": "m"}
    )
    result = rewriter.rewrite(
        "zh",
        "en",
        {},
        "src",
        {"lines": 1, "syllables_per_line": [1]},
        max_rounds=1,
    )
    assert result["status"] == "error"


def test_editor_result_dataclass() -> None:
    """EditorResult 保存结果."""
    draft = tools.TemplateDraft()
    result = EditorResult(draft, True, "ok")
    assert result.draft is draft and result.submitted and result.message == "ok"


def test_editor_stub_client_unused_path() -> None:
    """StubLLMClient 作为 editor 客户端时也能构造（接口一致性）."""
    stub = StubLLMClient("u", "k", "m")
    assert stub.base_url == "u"
