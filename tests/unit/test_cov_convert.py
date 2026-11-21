# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""统一模板转化模块（src.templates.convert）的单元测试.

覆盖：约束值归一化、音节数/约束表规整、映射校验、单元格转换、
完整模板转化（押韵与自定义代码复制）以及内置模板韵式声明合法性。
"""

from typing import Any, ClassVar

import pytest

from src.templates import PoetryTemplate, _registry, register
from src.templates import convert as conv
from src.templates.rhyme import normalize_rhyme_scheme


def _cell(**attributes: str) -> dict[str, Any]:
    """构造约束单元格（默认三属性齐全）."""
    attrs = {"tone": "", "stress": "", "length": ""}
    attrs.update(attributes)
    return {"onset": "", "nucleus": "", "coda": "", "attributes": attrs}


def _free() -> dict[str, Any]:
    """构造空约束单元格."""
    return _cell()


# --------------------------------------------------------------------------- #
# 基础辅助
# --------------------------------------------------------------------------- #
def test_constraint_scheme_known_and_unknown() -> None:
    """已知语言返回属性维度，未知语言返回空维度."""
    assert conv.constraint_scheme("zh") == ("tone", ("平", "仄"))
    assert conv.constraint_scheme("xx") == ("", ())


def test_normalize_constraint_value_branches() -> None:
    """约束值归一化：空/规范值/别名/非法/无维度语言."""
    assert conv.normalize_constraint_value("zh", "") == ""
    assert conv.normalize_constraint_value("zh", "平") == "平"
    assert conv.normalize_constraint_value("en", "重") == "heavy"
    assert conv.normalize_constraint_value("la", "短") == "short"
    assert conv.normalize_constraint_value("en", "??") is None
    assert conv.normalize_constraint_value("fr", "平") == ""


def test_normalize_syllables_padding() -> None:
    """音节数规整：截断/补齐/容错."""
    assert conv._normalize_syllables({"syllables_per_line": [3, 4, 5]}, 2) == [3, 4]
    assert conv._normalize_syllables({"syllables_per_line": [3]}, 3) == [3, 3, 3]
    assert conv._normalize_syllables({}, 2) == [7, 7]
    assert conv._normalize_syllables({"syllables_per_line": [0, "bad"]}, 2) == [1, 7]


def test_source_tables_prefers_alternatives() -> None:
    """有 alternatives 时使用全部约束表并补齐每行单元格."""
    table1 = [[_cell(tone="平")], []]
    table2 = [[_cell(tone="仄")], [_cell(tone="平")]]
    source = {
        "syllable_constraint_alternatives": [table1, table2],
        "syllable_constraints": table1,
    }
    tables = conv._source_tables(source, 2, [2, 1])
    assert len(tables) == 2
    assert len(tables[0]) == 2
    assert len(tables[0][0]) == 2
    assert tables[0][0][1] == {}
    assert tables[0][1] == [{}]
    assert len(tables[1][0]) == 2


def test_source_tables_single_and_missing() -> None:
    """无 alternatives 时使用单表；无约束时返回一份空表."""
    single = conv._source_tables({"syllable_constraints": [[_cell(tone="平")]]}, 1, [1])
    assert len(single) == 1 and single[0][0][0]["attributes"]["tone"] == "平"
    empty = conv._source_tables({}, 1, [2])
    assert empty == [[[{}, {}]]]


def test_source_tables_tolerates_bad_rows() -> None:
    """约束表中的非列表行/非字典单元格被容错."""
    source = {"syllable_constraints": [[{"attributes": "bad"}, "x"], "bad-row"]}
    tables = conv._source_tables(source, 2, [2, 1])
    assert tables[0][0] == [{"attributes": "bad"}, {}]
    assert tables[0][1] == [{}]


def test_normalize_mapping_branches() -> None:
    """映射校验：None、非对象、非法源/目标值、别名、合法."""
    assert conv._normalize_mapping(None, "zh", "en") == ({}, None)
    mapping, error = conv._normalize_mapping([], "zh", "en")
    assert mapping == {} and error is not None
    mapping, error = conv._normalize_mapping({"??": "heavy"}, "zh", "en")
    assert mapping == {} and error is not None and "源属性值" in error
    mapping, error = conv._normalize_mapping({"平": "??"}, "zh", "en")
    assert mapping == {} and error is not None and "目标属性值" in error
    mapping, error = conv._normalize_mapping({"平": "重", "": "heavy"}, "zh", "en")
    assert error is None
    assert mapping == {"平": "heavy"}


def test_convert_cell_branches() -> None:
    """单元格转换：正常映射、缺失源值、目标无属性、映射值非法."""
    mapping = {"平": "heavy"}
    converted = conv._convert_cell(
        _cell(tone="平", onset="zh"), "tone", "stress", ("light", "heavy"), mapping
    )
    assert converted["attributes"]["stress"] == "heavy"
    assert converted["onset"] == ""
    missing = conv._convert_cell(_cell(), "tone", "stress", ("light",), mapping)
    assert missing["attributes"]["stress"] == ""
    no_target = conv._convert_cell(
        _cell(tone="平"), "tone", "", ("light", "heavy"), mapping
    )
    assert no_target["attributes"] == {"tone": "", "stress": "", "length": ""}
    invalid = conv._convert_cell(
        _cell(tone="平"), "tone", "stress", ("light",), mapping
    )
    assert invalid["attributes"]["stress"] == ""


# --------------------------------------------------------------------------- #
# 完整模板转化
# --------------------------------------------------------------------------- #
def test_convert_template_errors() -> None:
    """未知目标语言/未知模板/非法映射均返回错误."""
    _, error = conv.convert_template("zh_wujue", "xx")
    assert error is not None and "目标语言" in error
    _, error = conv.convert_template("nope", "en")
    assert error is not None and "未知模板" in error
    _, error = conv.convert_template("zh_xiangjianhuan", "en", {"??": "heavy"})
    assert error is not None


def test_convert_builtin_sonnet_carries_rhyme() -> None:
    """内置商籁体转化：行数/音节/押韵韵式复制，仅约束属性值转换."""
    spec, error = conv.convert_template(
        "en_sonnet", "zh", {"light": "平", "heavy": "仄"}
    )
    assert error is None
    assert spec["status"] == "ok"
    assert spec["source_name"] == "莎士比亚商籁体"
    assert spec["source_language"] == "en"
    assert spec["language"] == "zh"
    assert spec["lines"] == 14
    assert spec["syllables_per_line"] == [10] * 14
    assert spec["rhyme_scheme"] == "ABABCDCDEFEFGG"
    assert spec["rhyme_distinct"] is False
    assert spec["code"] == ""
    assert len(spec["alternatives"]) == 1
    values = {
        cell["attributes"]["tone"]
        for row in spec["alternatives"][0]
        for cell in row
        if cell["attributes"]["tone"]
    }
    assert values <= {"平", "仄"}
    assert values


def test_convert_custom_template_carries_rhyme_and_code() -> None:
    """自定义模板转化：多约束/韵式/自定义代码均复制."""

    class _Custom(PoetryTemplate):
        """带韵式与代码的测试模板."""

        name = "自定义测试"
        language = "zh"
        lines = 2
        syllables_per_line: ClassVar[list[int]] = [2, 2]
        rhyme_scheme = "AB"
        rhyme_distinct = True
        custom_code = "errors.append('x')"

        def get_syllable_constraint_alternatives(
            self,
        ) -> list[list[list[dict[str, Any]]]]:
            """两份约束表."""
            return [
                [[_cell(tone="平"), _free()], [_cell(tone="仄"), _free()]],
                [[_cell(tone="仄"), _free()], [_cell(tone="平"), _free()]],
            ]

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """第一份约束表."""
            return self.get_syllable_constraint_alternatives()[0]

    register("test_convert_custom", _Custom())
    try:
        spec, error = conv.convert_template(
            "test_convert_custom", "la", {"平": "long", "仄": "short"}
        )
        assert error is None
        assert spec["rhyme_scheme"] == "AB"
        assert spec["rhyme_distinct"] is True
        assert spec["code"] == "errors.append('x')"
        assert len(spec["alternatives"]) == 2
        assert spec["source_name"] == "自定义测试"
    finally:
        _registry.pop("test_convert_custom", None)


def test_convert_drops_invalid_source_scheme() -> None:
    """源模板韵式与行数不匹配时丢弃韵式（避免生成非法模板）."""

    class _BadScheme(PoetryTemplate):
        """韵式长度错误的测试模板."""

        name = "坏韵式"
        language = "zh"
        lines = 3
        syllables_per_line: ClassVar[list[int]] = [2, 2, 2]
        rhyme_scheme = "AB"
        rhyme_distinct = True

    register("test_convert_bad_scheme", _BadScheme())
    try:
        spec, error = conv.convert_template("test_convert_bad_scheme", "en")
        assert error is None
        assert spec["rhyme_scheme"] == ""
        assert spec["rhyme_distinct"] is False
    finally:
        _registry.pop("test_convert_bad_scheme", None)


def test_convert_tolerates_bad_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """源模板行数字段非法时回退默认行数."""

    class _Fake:
        """返回非法行数的假模板."""

        def to_dict(self) -> dict[str, Any]:
            """返回 lines 非法的模板字典."""
            return {
                "name": "坏行数",
                "language": "zh",
                "lines": "bad",
                "syllables_per_line": [2],
                "syllable_constraints": None,
                "syllable_constraint_alternatives": None,
                "rhyme_scheme": "",
                "rhyme_distinct": False,
                "custom_code": "",
            }

    monkeypatch.setattr(conv, "get_template", lambda key: _Fake())
    spec, error = conv.convert_template("any", "en")
    assert error is None
    assert spec["lines"] == 4


def test_constraint_tables_to_values() -> None:
    """约束字典表转值表：中文属性、无属性语言、非字典单元格."""
    tables = [[[_cell(tone="平"), _cell()]]]
    assert conv.constraint_tables_to_values(tables, "zh") == [[["平", ""]]]
    assert conv.constraint_tables_to_values(tables, "en") == [[["", ""]]]
    assert conv.constraint_tables_to_values([[[{"attributes": "bad"}]]], "zh") == [
        [[""]]
    ]


# --------------------------------------------------------------------------- #
# 内置模板的韵式声明
# --------------------------------------------------------------------------- #
def test_builtin_rhyme_schemes_are_valid() -> None:
    """所有内置模板声明的韵式长度必须与行数一致（保证可安全转化）."""
    checked = 0
    for template in list(_registry.values()):
        scheme = template.rhyme_scheme
        if not scheme:
            continue
        cleaned, error = normalize_rhyme_scheme(scheme, template.lines)
        assert error is None, (template.name, scheme, error)
        assert len(cleaned) == template.lines
        checked += 1
    assert checked >= 15


@pytest.mark.parametrize(
    ("key", "scheme"),
    [
        ("zh_wujue", "-A-A"),
        ("zh_qijue", "-A-A"),
        ("zh_wulv", "-A-A-A-A"),
        ("zh_qilv", "-A-A-A-A"),
        ("zh_xiangjianhuan", "AAABBAA"),
        ("zh_rumengling", "AA-AAAA"),
        ("zh_langtaosha", "AAA-AAAA-A"),
        ("zh_qingpingyue", "AAAABB-B"),
        ("en_sonnet", "ABABCDCDEFEFGG"),
        ("en_villanelle", "ABAABAABAABAABAABAA"),
        ("en_heroic_couplet", "AA"),
        ("fr_rondeau", "AABBAAABAAABBAA"),
        ("fr_triolet", "ABAAABAB"),
        ("fr_ballade", "ABABBCBCABABBCBCABABBCBCBCBC"),
        ("it_terza_rima", "ABABCBCDCDEDEE"),
        ("it_ottava_rima", "ABABABCC"),
        ("la_distichon", "AA"),
    ],
)
def test_builtin_rhyme_scheme_values(key: str, scheme: str) -> None:
    """内置模板韵式声明与模板逻辑一致（用于跨语言复制押韵）."""
    assert _registry[key].rhyme_scheme == scheme


def test_to_dict_includes_conversion_fields() -> None:
    """模板字典包含押韵/自定义代码/结构规则字段（供转化复制）."""

    class _Plain(PoetryTemplate):
        """最简模板."""

        name = "plain"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    data = _Plain().to_dict()
    assert data["rhyme_scheme"] == ""
    assert data["rhyme_distinct"] is False
    assert data["custom_code"] == ""
    assert data["structural_rules"] is None
    assert data["special_rules"] == []
    assert data["rule_note"] == ""
    assert data["rule_description"] == ""


def test_convert_carries_rule_note() -> None:
    """模板规则描述随转化复制，并计入“已携带”清单."""

    class _WithNote(PoetryTemplate):
        """带规则描述的测试模板."""

        name = "带描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        rule_note = "上下联需对仗，意境清远。"

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """一份自由约束."""
            return [[_free(), _free()]]

    register("test_convert_note", _WithNote())
    try:
        spec, error = conv.convert_template("test_convert_note", "en")
        assert error is None
        assert spec["rule_note"] == "上下联需对仗，意境清远。"
        assert "rule_note" in spec["carried_rules"]
    finally:
        _registry.pop("test_convert_note", None)


def test_describe_includes_rule_note() -> None:
    """模板规则描述会进入 describe()（即写作 AI 的 prompt）."""

    class _WithNote(PoetryTemplate):
        """带规则描述的测试模板."""

        name = "描述模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "需要注意对仗与领字。"

    assert "需要注意对仗与领字。" in _WithNote().describe()


# --------------------------------------------------------------------------- #
# 数据化结构规则的转化
# --------------------------------------------------------------------------- #
def test_convert_jinti_carries_structural_rules() -> None:
    """绝句转化：结构规则（平仄骨架/三平尾/孤平）按映射换成目标语言属性值."""
    spec, error = conv.convert_template(
        "zh_wujue", "en", {"平": "heavy", "仄": "light"}
    )
    assert error is None
    rules = spec["structural_rules"]
    assert rules is not None
    assert rules["kind"] == "jinti"
    assert rules["attribute"] == "stress"
    assert rules["level_value"] == "heavy"
    assert rules["oblique_value"] == "light"
    assert rules["positions"] == [1, 3]
    assert rules["rhyme_lines"] == [1, 3]
    assert rules["forbid_sanpingwei"] is True
    assert rules["forbid_guping"] is True
    assert "jinti" in spec["carried_rules"]
    assert spec["dropped_rules"] == []


def test_convert_reuses_builtin_description() -> None:
    """转化后直接复用内置模板的规则描述，供用户继续修改."""
    source = _registry["zh_wujue"]
    spec, error = conv.convert_template(
        "zh_wujue", "en", {"平": "heavy", "仄": "light"}
    )
    assert error is None
    assert source.rule_description
    assert spec["rule_note"] == source.rule_description.strip()
    assert "rule_note" in spec["carried_rules"]


def test_convert_prefers_rule_note_over_description() -> None:
    """用户自填的规则描述优先于模板自动描述."""

    class _Both(PoetryTemplate):
        """同时带用户描述与自动描述的测试模板."""

        name = "双描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "用户自填描述"
        rule_description = "自动摘要描述"

    register("test_convert_both", _Both())
    try:
        spec, error = conv.convert_template("test_convert_both", "en")
        assert error is None
        assert spec["rule_note"] == "用户自填描述"
    finally:
        _registry.pop("test_convert_both", None)


def test_convert_empty_description_stays_empty() -> None:
    """源模板既无规则描述也无摘要时，转化结果为空."""

    class _NoNote(PoetryTemplate):
        """无描述测试模板."""

        name = "无描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]

    register("test_convert_nonote", _NoNote())
    try:
        spec, error = conv.convert_template("test_convert_nonote", "en")
        assert error is None
        assert spec["rule_note"] == ""
    finally:
        _registry.pop("test_convert_nonote", None)


def test_convert_jinti_identity_values() -> None:
    """同语言转化时结构规则属性与值保持不变."""
    spec, error = conv.convert_template("zh_wujue", "zh", {"平": "平", "仄": "仄"})
    assert error is None
    assert spec["structural_rules"]["attribute"] == "tone"
    assert spec["structural_rules"]["level_value"] == "平"


def test_convert_jinti_drop_reasons() -> None:
    """映射不完整/目标语言无属性/映射退化时结构规则不携带并给出原因."""
    spec, error = conv.convert_template("zh_wujue", "en", {"平": "heavy"})
    assert error is None
    assert spec["structural_rules"] is None
    assert any("映射未覆盖" in rule for rule in spec["dropped_rules"])

    spec, error = conv.convert_template("zh_wujue", "fr", {"平": "平"})
    assert error is None
    assert spec["structural_rules"] is None
    assert any("没有可对应的音节属性" in rule for rule in spec["dropped_rules"])

    spec, error = conv.convert_template(
        "zh_wujue", "en", {"平": "heavy", "仄": "heavy"}
    )
    assert error is None
    assert spec["structural_rules"] is None
    assert any("同一目标值" in rule for rule in spec["dropped_rules"])


def test_convert_invalid_source_structural_dropped() -> None:
    """源模板结构规则数据非法时不崩溃，按未携带处理."""

    class _BadRules(PoetryTemplate):
        """结构规则非法的测试模板."""

        name = "坏结构规则"
        language = "zh"
        lines = 2
        syllables_per_line: ClassVar[list[int]] = [2, 2]
        structural_rules: ClassVar[dict[str, Any]] = {"kind": "unknown"}

    register("test_bad_structural", _BadRules())
    try:
        spec, error = conv.convert_template("test_bad_structural", "en")
        assert error is None
        assert spec["structural_rules"] is None
        assert any("结构规则无效" in rule for rule in spec["dropped_rules"])
    finally:
        _registry.pop("test_bad_structural", None)


def test_convert_reports_dropped_special_rules() -> None:
    """源模板的语言专属特殊规则会列入“未携带”清单."""
    spec, error = conv.convert_template(
        "zh_rumengling", "en", {"平": "heavy", "仄": "light"}
    )
    assert error is None
    assert spec["dropped_rules"]
    assert any("叠句" in rule for rule in spec["dropped_rules"])


def test_convert_multi_kinds_carried_codes() -> None:
    """多约束 + 自定义代码的转化会报告对应的携带项."""

    class _Multi(PoetryTemplate):
        """多约束模板."""

        name = "多约束"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        custom_code = "pass"

        def get_syllable_constraint_alternatives(
            self,
        ) -> list[list[list[dict[str, Any]]]]:
            """两份约束表."""
            return [[[_cell(tone="平"), _free()]], [[_cell(tone="仄"), _free()]]]

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """第一份约束表."""
            return self.get_syllable_constraint_alternatives()[0]

    register("test_convert_multi", _Multi())
    try:
        spec, error = conv.convert_template("test_convert_multi", "en")
        assert error is None
        assert "multiple_kinds" in spec["carried_rules"]
        assert "custom_code" in spec["carried_rules"]
    finally:
        _registry.pop("test_convert_multi", None)
