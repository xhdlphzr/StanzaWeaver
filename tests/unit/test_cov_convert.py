# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the unified template conversion module (convert).

Cover constraint-value normalization, syllable/constraint-table shaping,
mapping validation, cell conversion, full template conversion (rhyme and
custom code copying) and built-in template rhyme-scheme validity.
"""

from typing import Any, ClassVar

import pytest

from src.templates import PoetryTemplate, _registry, register
from src.templates import convert as conv
from src.templates.rhyme import normalize_rhyme_scheme


def _cell(**attributes: str) -> dict[str, Any]:
    """Build a constraint cell with all three attributes by default."""
    attrs = {"tone": "", "stress": "", "length": ""}
    attrs.update(attributes)
    return {"onset": "", "nucleus": "", "coda": "", "attributes": attrs}


def _free() -> dict[str, Any]:
    """Build an empty constraint cell."""
    return _cell()


# --------------------------------------------------------------------------- #
# Basic helpers
# --------------------------------------------------------------------------- #
def test_constraint_scheme_known_and_unknown() -> None:
    """Known languages return their attribute axis; unknown ones return empty."""
    assert conv.constraint_scheme("zh") == ("tone", ("平", "仄"))
    assert conv.constraint_scheme("xx") == ("", ())


def test_normalize_constraint_value_branches() -> None:
    """Constraint value normalization: empty/canonical/alias/invalid/none."""
    assert conv.normalize_constraint_value("zh", "") == ""
    assert conv.normalize_constraint_value("zh", "平") == "平"
    assert conv.normalize_constraint_value("en", "重") == "heavy"
    assert conv.normalize_constraint_value("la", "短") == "short"
    assert conv.normalize_constraint_value("en", "??") is None
    assert conv.normalize_constraint_value("fr", "平") == ""


def test_normalize_syllables_padding() -> None:
    """Syllable count shaping: truncate/pad/tolerate bad values."""
    assert conv._normalize_syllables({"syllables_per_line": [3, 4, 5]}, 2) == [3, 4]
    assert conv._normalize_syllables({"syllables_per_line": [3]}, 3) == [3, 3, 3]
    assert conv._normalize_syllables({}, 2) == [7, 7]
    assert conv._normalize_syllables({"syllables_per_line": [0, "bad"]}, 2) == [1, 7]


def test_source_tables_prefers_alternatives() -> None:
    """With alternatives, use every constraint table and pad each row."""
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
    """Without alternatives use one table; with no constraints return empty."""
    single = conv._source_tables({"syllable_constraints": [[_cell(tone="平")]]}, 1, [1])
    assert len(single) == 1 and single[0][0][0]["attributes"]["tone"] == "平"
    empty = conv._source_tables({}, 1, [2])
    assert empty == [[[{}, {}]]]


def test_source_tables_tolerates_bad_rows() -> None:
    """Non-list rows and non-dict cells in constraint tables are tolerated."""
    source = {"syllable_constraints": [[{"attributes": "bad"}, "x"], "bad-row"]}
    tables = conv._source_tables(source, 2, [2, 1])
    assert tables[0][0] == [{"attributes": "bad"}, {}]
    assert tables[0][1] == [{}]


def test_normalize_mapping_branches() -> None:
    """Mapping validation: None, non-object, invalid source/target, valid."""
    assert conv._normalize_mapping(None, "zh", "en") == ({}, None)
    mapping, error = conv._normalize_mapping([], "zh", "en")
    assert mapping == {} and error is not None
    mapping, error = conv._normalize_mapping({"??": "heavy"}, "zh", "en")
    assert mapping == {} and error is not None
    assert "Invalid source attribute value" in error
    mapping, error = conv._normalize_mapping({"平": "??"}, "zh", "en")
    assert mapping == {} and error is not None
    assert "Invalid target attribute value" in error
    mapping, error = conv._normalize_mapping({"平": "重", "": "heavy"}, "zh", "en")
    assert error is None
    assert mapping == {"平": "heavy"}


def test_convert_cell_branches() -> None:
    """Cell conversion: normal mapping, missing value, no target attribute."""
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
# Full template conversion
# --------------------------------------------------------------------------- #
def test_convert_template_errors() -> None:
    """Unknown target language, unknown template and bad mapping error out."""
    _, error = conv.convert_template("zh_wujue", "xx")
    assert error is not None and "Unsupported target language" in error
    _, error = conv.convert_template("nope", "en")
    assert error is not None and "Unknown template" in error
    _, error = conv.convert_template("zh_xiangjianhuan", "en", {"??": "heavy"})
    assert error is not None


def test_convert_builtin_sonnet_carries_rhyme() -> None:
    """Built-in sonnet conversion: copy lines/syllables/rhyme, remap values."""
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
    """Custom template conversion: multi-constraints, rhyme and code copied."""

    class _Custom(PoetryTemplate):
        """Test template with a rhyme scheme and custom code."""

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
            """Two constraint tables."""
            return [
                [[_cell(tone="平"), _free()], [_cell(tone="仄"), _free()]],
                [[_cell(tone="仄"), _free()], [_cell(tone="平"), _free()]],
            ]

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """First constraint table."""
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
    """Drop a source rhyme scheme that does not match the line count."""

    class _BadScheme(PoetryTemplate):
        """Test template with a wrong-length rhyme scheme."""

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
    """Fall back to the default line count when source lines are invalid."""

    class _Fake:
        """Fake template returning an invalid line count."""

        def to_dict(self) -> dict[str, Any]:
            """Return a template dict whose lines field is invalid."""
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
    """Constraint dict tables to value tables: attributes and bad cells."""
    tables = [[[_cell(tone="平"), _cell()]]]
    assert conv.constraint_tables_to_values(tables, "zh") == [[["平", ""]]]
    assert conv.constraint_tables_to_values(tables, "en") == [[["", ""]]]
    assert conv.constraint_tables_to_values([[[{"attributes": "bad"}]]], "zh") == [
        [[""]]
    ]


# --------------------------------------------------------------------------- #
# Built-in template rhyme-scheme declarations
# --------------------------------------------------------------------------- #
def test_builtin_rhyme_schemes_are_valid() -> None:
    """Every built-in rhyme scheme must match its line count (safe to convert)."""
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
    """Built-in rhyme-scheme declarations match template logic (safe copies)."""
    assert _registry[key].rhyme_scheme == scheme


def test_to_dict_includes_conversion_fields() -> None:
    """Template dict includes rhyme, custom code and structural rule fields."""

    class _Plain(PoetryTemplate):
        """Minimal template."""

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
    """Rule notes are copied by conversion and listed as carried."""

    class _WithNote(PoetryTemplate):
        """Test template with a rule description."""

        name = "带描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        rule_note = "上下联需对仗，意境清远。"

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """One free constraint row."""
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
    """Rule notes flow into describe() (the writing AI's prompt)."""

    class _WithNote(PoetryTemplate):
        """Test template with a rule description."""

        name = "描述模板"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "需要注意对仗与领字。"

    assert "需要注意对仗与领字。" in _WithNote().describe()


# --------------------------------------------------------------------------- #
# Conversion of data-driven structural rules
# --------------------------------------------------------------------------- #
def test_convert_jinti_carries_structural_rules() -> None:
    """Quatrain conversion remaps structural rules to target-language values."""
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
    """Conversion reuses the built-in rule note so users can keep editing."""
    source = _registry["zh_wujue"]
    spec, error = conv.convert_template(
        "zh_wujue", "en", {"平": "heavy", "仄": "light"}
    )
    assert error is None
    assert source.rule_description
    assert spec["rule_note"] == source.rule_description.strip()
    assert "rule_note" in spec["carried_rules"]


def test_convert_prefers_rule_note_over_description() -> None:
    """A user-provided rule note wins over the template's automatic one."""

    class _Both(PoetryTemplate):
        """Test template with both a user note and an automatic description."""

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
    """No rule note or description on the source yields an empty result."""

    class _NoNote(PoetryTemplate):
        """Test template without any description."""

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
    """Same-language conversion keeps structural rule attributes and values."""
    spec, error = conv.convert_template("zh_wujue", "zh", {"平": "平", "仄": "仄"})
    assert error is None
    assert spec["structural_rules"]["attribute"] == "tone"
    assert spec["structural_rules"]["level_value"] == "平"


def test_convert_jinti_drop_reasons() -> None:
    """Incomplete/attribute-less/degenerate mappings drop rules with a reason."""
    spec, error = conv.convert_template("zh_wujue", "en", {"平": "heavy"})
    assert error is None
    assert spec["structural_rules"] is None
    assert any("does not cover" in rule for rule in spec["dropped_rules"])

    spec, error = conv.convert_template("zh_wujue", "fr", {"平": "平"})
    assert error is None
    assert spec["structural_rules"] is None
    assert any(
        "no matching syllable attribute" in rule for rule in spec["dropped_rules"]
    )

    spec, error = conv.convert_template(
        "zh_wujue", "en", {"平": "heavy", "仄": "heavy"}
    )
    assert error is None
    assert spec["structural_rules"] is None
    assert any("same target value" in rule for rule in spec["dropped_rules"])


def test_convert_invalid_source_structural_dropped() -> None:
    """Invalid source structural rules do not crash; they are not carried."""

    class _BadRules(PoetryTemplate):
        """Test template with invalid structural rules."""

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
        assert any(
            "structural rules are invalid" in rule for rule in spec["dropped_rules"]
        )
    finally:
        _registry.pop("test_bad_structural", None)


def test_convert_reports_dropped_special_rules() -> None:
    """Language-specific special rules are listed in the dropped rules."""
    spec, error = conv.convert_template(
        "zh_rumengling", "en", {"平": "heavy", "仄": "light"}
    )
    assert error is None
    assert spec["dropped_rules"]
    assert any("identical refrain" in rule for rule in spec["dropped_rules"])


def test_convert_multi_kinds_carried_codes() -> None:
    """Multi-constraint plus custom-code conversion reports carried items."""

    class _Multi(PoetryTemplate):
        """Multi-constraint template."""

        name = "多约束"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [2]
        custom_code = "pass"

        def get_syllable_constraint_alternatives(
            self,
        ) -> list[list[list[dict[str, Any]]]]:
            """Two constraint tables."""
            return [[[_cell(tone="平"), _free()]], [[_cell(tone="仄"), _free()]]]

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """First constraint table."""
            return self.get_syllable_constraint_alternatives()[0]

    register("test_convert_multi", _Multi())
    try:
        spec, error = conv.convert_template("test_convert_multi", "en")
        assert error is None
        assert "multiple_kinds" in spec["carried_rules"]
        assert "custom_code" in spec["carried_rules"]
    finally:
        _registry.pop("test_convert_multi", None)
