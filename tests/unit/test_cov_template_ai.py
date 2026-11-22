# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the newly added template-editing AI modules.

Coverage: the editor config endpoint, multi-constraint template descriptions,
MeterValidator multi-constraint branches, the generic rhyme module, template
tools, and the template-editing AI agent.
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
    """Build an empty constraint cell."""
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": {"tone": "", "stress": "", "length": ""},
    }


def _zh(tone: str) -> dict[str, Any]:
    """Build a Chinese tone constraint cell."""
    cell = _syl()
    cell["attributes"]["tone"] = tone
    return cell


def _empty_syl() -> Syllable:
    """Build an empty syllable."""
    return Syllable(
        onset="",
        nucleus="",
        coda="",
        attributes={"tone": "", "stress": "", "length": ""},
    )


# --------------------------------------------------------------------------- #
# Editor config endpoint
# --------------------------------------------------------------------------- #
def test_config_editor_defaults_and_setter(tmp_path: Path) -> None:
    """Editor falls back to defaults; the setter writes config data."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    assert cfg.editor["model"] == config_module.DEFAULT_EDITOR["model"]
    cfg.editor = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["editor"]["model"] == "m"
    assert cfg.editor["api_key"] == "k"


def test_config_editor_non_dict_falls_back(tmp_path: Path) -> None:
    """A non-dict editor field falls back to defaults."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"editor": [1, 2]}
    cfg._loaded = True
    assert cfg.editor["model"] == config_module.DEFAULT_EDITOR["model"]


# --------------------------------------------------------------------------- #
# Template descriptions: alternatives and base methods
# --------------------------------------------------------------------------- #
class _AltTemplate(PoetryTemplate):
    """Template used to test alternative serialization/description."""

    name = "多约束"
    language = "zh"
    lines = 2
    syllables_per_line: ClassVar[list[int]] = [2, 2]

    def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
        """Return the first constraint table."""
        return [[_zh("平"), _syl()], [_zh("仄"), _syl()]]

    def get_syllable_constraint_alternatives(self) -> list[list[list[dict[str, Any]]]]:
        """Return two constraint tables."""
        return [
            self.get_syllable_constraints(),
            [[_zh("仄"), _syl()], [_syl(), _syl()]],
        ]


class _BareAlt(PoetryTemplate):
    """Template that does not override the alternatives method."""

    name = "bare"
    language = "zh"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [1]


def test_base_alternatives_default_none() -> None:
    """The base class has no alternatives by default."""
    assert _BareAlt().get_syllable_constraint_alternatives() is None


def test_describe_dict_with_alternatives() -> None:
    """describe_template_from_dict supports alternatives (tolerates empty)."""
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
    assert "syllable constraint variants" in desc
    assert "Constraint variant 1" in desc
    assert "Constraint variant 2" in desc
    assert "tone=平" in desc


def test_describe_dict_single_table() -> None:
    """Falls back to the single-table description without alternatives."""
    desc = describe_template_from_dict(
        {
            "lines": 1,
            "syllables_per_line": [1],
            "syllable_constraints": [[_zh("仄")]],
        }
    )
    assert "tone=仄" in desc
    assert "Constraint variant" not in desc


def test_alt_template_to_dict_and_describe() -> None:
    """An alternative template's to_dict/describe include alternatives."""
    tpl = _AltTemplate()
    data = tpl.to_dict()
    assert data["syllable_constraints"] is not None
    assert len(data["syllable_constraint_alternatives"]) == 2
    assert "syllable constraint variants" in tpl.describe()


def test_describe_constraint_table_skips_non_dict_cells() -> None:
    """_describe_constraint_table tolerates non-dict cells."""
    desc = _describe_constraint_table([1], [[_syl(), _syl()]])
    assert "Line 1" in desc


# --------------------------------------------------------------------------- #
# MeterValidator: alternatives (OR semantics)
# --------------------------------------------------------------------------- #
def _alt_template_dict(
    alternatives: list[list[list[dict[str, Any]]]],
) -> dict[str, Any]:
    """Build a template dict with alternatives."""
    return {
        "name": "多约束测试",
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [2, 2],
        "syllable_constraints": alternatives[0],
        "syllable_constraint_alternatives": alternatives,
    }


def test_validator_alternatives_second_matches() -> None:
    """Passes when the first table fails and the second succeeds."""
    alternatives = [
        [[_zh("仄"), _syl()], [_zh("平"), _syl()]],
        [[_zh("平"), _syl()], [_zh("仄"), _syl()]],
    ]
    result = MeterValidator().validate(
        ["山风", "月雪"], _alt_template_dict(alternatives)
    )
    assert result.passed, result.errors


def test_validator_alternatives_none_match_reports_best() -> None:
    """Returns the errors of the table with the fewest errors when none match."""
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
    """Alternative checks report a line that has no syllables."""
    alternatives = [[[_zh("平")], [_zh("平")]]]
    result = MeterValidator().validate(["abc", "abc"], _alt_template_dict(alternatives))
    assert not result.passed
    assert any("no syllables" in e for e in result.errors)


def test_validator_alternatives_none_when_missing() -> None:
    """Returns an empty list when the alternatives key is missing (early return)."""
    assert MeterValidator()._constraint_alternatives({}) == []


def test_validate_line_alternatives_match_second() -> None:
    """Single-line check: passes when the second table is satisfied."""
    alternatives = [
        [[_zh("仄"), _syl()], [_syl(), _syl()]],
        [[_zh("平"), _syl()], [_syl(), _syl()]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_no_match() -> None:
    """Single-line check: reports errors when no table matches."""
    alternatives = [
        [[_zh("平"), _zh("仄")], [_syl(), _syl()]],
        [[_zh("仄"), _zh("平")], [_syl(), _syl()]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert not result.passed
    assert result.errors


def test_validate_line_alternatives_short_table_is_free() -> None:
    """Single-line check: a table shorter than the line index counts as free."""
    alternatives = [
        [[_zh("仄")]],
        [[_zh("平")]],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 1, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_empty_line_constraints() -> None:
    """Single-line check: an empty row counts as unconstrained (passes)."""
    alternatives = [
        [[], [_zh("仄")]],
        [[_zh("仄")], []],
    ]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("山风", 0, template)
    assert result.passed, result.errors


def test_validate_line_alternatives_empty_variants() -> None:
    """Single-line check: no per-position errors without syllables."""
    alternatives = [[[_zh("平")], [_zh("平")]]]
    template = _alt_template_dict(alternatives)
    result = MeterValidator().validate_line("abc", 0, template)
    assert not result.passed
    assert len(result.errors) == 1


# --------------------------------------------------------------------------- #
# Generic rhyme module
# --------------------------------------------------------------------------- #
def test_last_word_variants() -> None:
    """Last-word extraction: word present / empty line."""
    assert rhyme_mod._last_word("The quick brown fox") == "fox"
    assert rhyme_mod._last_word("") == ""
    assert rhyme_mod._last_word("don't stop") == "stop"


def test_syllable_rhyme_key_empty() -> None:
    """Generic syllable rhyme key: empty nucleus/coda returns an empty string."""
    assert rhyme_mod._syllable_rhyme_key(_empty_syl()) == ""
    assert (
        rhyme_mod._syllable_rhyme_key(
            Syllable(onset="", nucleus="a", coda="n", attributes={})
        )
        == "an"
    )


def test_rhyme_keys_english() -> None:
    """English builds keys from stressed tails; blank lines return None."""
    keys = rhyme_mod.rhyme_keys("en", "a light")
    assert keys is not None
    assert all(k.startswith("en:") for k in keys)
    assert rhyme_mod.rhyme_keys("en", "!!!") is None


def test_rhyme_keys_french() -> None:
    """French builds keys from the final vowel nucleus; blank returns None."""
    keys = rhyme_mod.rhyme_keys("fr", "il parle")
    assert keys is not None
    assert all(k.startswith("fr:") for k in keys)
    assert rhyme_mod.rhyme_keys("fr", "!!!") is None


def test_rhyme_keys_zh_with_and_without_syllables() -> None:
    """Chinese uses given syllables or analyzes itself; blank returns None."""
    keys = rhyme_mod.rhyme_keys("zh", "风")
    assert keys is not None and keys == {"zh:庚"}
    provided = [Syllable(onset="d", nucleus="e", coda="ng", attributes={})]
    assert rhyme_mod.rhyme_keys("zh", "灯", provided) == {"zh:庚"}
    assert rhyme_mod.rhyme_keys("zh", "") is None
    assert rhyme_mod.rhyme_keys("zh", "风", [_empty_syl()]) is None


def test_rhyme_keys_generic_language() -> None:
    """Other languages use nucleus+coda; no syllables returns None."""
    provided = [Syllable(onset="c", nucleus="a", coda="", attributes={})]
    assert rhyme_mod.rhyme_keys("it", "casa", provided) == {"it:a"}
    assert rhyme_mod.rhyme_keys("it", "") is None
    assert rhyme_mod.rhyme_keys("it", "casa", [_empty_syl()]) is None


def test_parse_rhyme_scheme() -> None:
    """Rhyme-scheme parsing supports separators and a no-rhyme marker."""
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
    """Scheme validation: empty, invalid chars, wrong length, valid."""
    assert rhyme_mod.normalize_rhyme_scheme("", 4) == ("", None)
    scheme, error = rhyme_mod.normalize_rhyme_scheme("A-B1", 3)
    assert scheme == "" and error is not None and "invalid character" in error
    scheme, error = rhyme_mod.normalize_rhyme_scheme("AB", 4)
    assert scheme == "" and error is not None and "length" in error
    assert rhyme_mod.normalize_rhyme_scheme("ABAB CDCD", 8) == ("ABABCDCD", None)


def test_check_rhyme_scheme_empty_and_too_long() -> None:
    """Empty schemes are skipped; a scheme longer than the poem errors."""
    assert rhyme_mod.check_rhyme_scheme("zh", ["春江"], "") == []
    errors = rhyme_mod.check_rhyme_scheme("zh", ["春江"], "AB")
    assert any("more than the poem's" in e for e in errors)


def test_check_rhyme_scheme_pass_and_mismatch() -> None:
    """A shared rhyme passes; different rhymes error."""
    good = ["春江花月风", "野渡无人灯"]
    assert rhyme_mod.check_rhyme_scheme("zh", good, "AA") == []
    bad = ["春江花月风", "野渡无人空"]
    errors = rhyme_mod.check_rhyme_scheme("zh", bad, "AA")
    assert any("mismatch" in e for e in errors)


def test_check_rhyme_scheme_unable_line_and_single_group() -> None:
    """Unresolvable lines error; single-line groups are skipped."""
    errors = rhyme_mod.check_rhyme_scheme("en", ["!!!", "???"], "AA")
    assert any("cannot determine the rhyme" in e for e in errors)
    assert rhyme_mod.check_rhyme_scheme("zh", ["春江花月风"], "A") == []


def test_check_rhyme_scheme_no_rhyme_marker() -> None:
    """Scheme '-' lines do not participate in rhyme checks."""
    poem = ["春江花月风", "-", "野渡无人灯"]
    assert rhyme_mod.check_rhyme_scheme("zh", poem, "A-A") == []


def test_check_rhyme_scheme_distinct() -> None:
    """Distinct groups: a shared rhyme errors, otherwise passes."""
    poem = ["a light", "a night", "a night", "a light"]
    errors = rhyme_mod.check_rhyme_scheme("en", poem, "ABAB", distinct=True)
    assert any("should be distinct" in e for e in errors)
    poem2 = ["a light", "a day", "a night", "the day"]
    assert rhyme_mod.check_rhyme_scheme("en", poem2, "ABAB", distinct=True) == []


def test_rhyme_scheme_description() -> None:
    """Scheme description: empty returns empty; otherwise grouped by 4 lines."""
    assert rhyme_mod.rhyme_scheme_description("") == ""
    assert "ABAB CDCD" in rhyme_mod.rhyme_scheme_description("abab cdcd")


# --------------------------------------------------------------------------- #
# Template tools: draft normalization and dispatch
# --------------------------------------------------------------------------- #
def test_draft_normalize_fixes_invalid_fields() -> None:
    """Draft normalization fixes illegal language/lines/syllables/values."""
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
    """Draft normalization pads missing cells and truncates extra kinds."""
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
    """Draft serialization and constraint-table conversion (zh and fr)."""
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
    """Building from a frontend draft tolerates illegal fields."""
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
    """Value normalization: empty, alias, illegal, no-dimension language."""
    assert normalize_constraint_value("zh", "") == ""
    assert normalize_constraint_value("zh", "平") == "平"
    assert normalize_constraint_value("en", "重") == "heavy"
    assert normalize_constraint_value("la", "短") == "short"
    assert normalize_constraint_value("en", "??") is None
    assert normalize_constraint_value("fr", "平") == ""


def test_execute_set_template_info() -> None:
    """Set template info: name/language/lines and error branches."""
    draft = tools.TemplateDraft()
    assert "error" in tools.execute_set_template_info(draft, {"name": " "})
    assert "error" in tools.execute_set_template_info(draft, {"language": "xx"})
    result = tools.execute_set_template_info(
        draft, {"name": "新模板", "language": "en", "lines": 5}
    )
    assert result["status"] == "ok"
    assert draft.name == "新模板" and draft.language == "en" and draft.lines == 5


def test_execute_set_syllables() -> None:
    """Set syllables per line: error branches and success."""
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
    """Set constraint kind count: illegal, growing, shrinking."""
    draft = tools.TemplateDraft()
    assert "error" in tools.execute_set_kind_count(draft, {"count": "x"})
    assert "error" in tools.execute_set_kind_count(draft, {"count": 0})
    assert "error" in tools.execute_set_kind_count(draft, {"count": 99})
    tools.execute_set_kind_count(draft, {"count": 3})
    assert len(draft.alternatives) == 3
    tools.execute_set_kind_count(draft, {"count": 1})
    assert len(draft.alternatives) == 1


def test_execute_set_constraints() -> None:
    """Fill constraints: error branches and success (out-of-range/bad rows)."""
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
    """Set the rhyme scheme and custom code."""
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
    """Building from a frontend draft accepts per-line syllable arrays."""
    draft = tools.draft_from_payload(
        {"language": "zh", "lines": 2, "syllables_per_line": [3, 4]}
    )
    assert draft.syllables_per_line == [3, 4]


def test_execute_set_from_template_converts() -> None:
    """Convert a Chinese template to English: copy lines/syllables, map values."""
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
    # The rhyme scheme is converted/copied along with the template.
    assert draft.rhyme_scheme == "AAABBAA"
    values = {
        value for table in draft.alternatives for row in table for value in row if value
    }
    assert values <= {"heavy", "light"}
    assert values


def test_execute_set_from_template_auto_fallback_value() -> None:
    """Without a mapping, values stay free while lines/syllables are still copied."""
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
    """A range takes the midpoint; free source templates stay unconstrained."""
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
    """Unknown template / empty key / invalid mapping value all error."""
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
    """set_from_template can be invoked through the unified dispatch."""
    draft = tools.TemplateDraft(language="en", lines=1)
    draft.normalize()
    result = tools.execute_template_tool(
        draft, "set_from_template", {"template_key": "zh_xiangjianhuan"}
    )
    assert result["status"] == "ok"


def test_convert_syllable_count_branches() -> None:
    """Syllable-count conversion branches for ranges/invalid values."""
    from src.templates.convert import convert_syllable_count

    assert convert_syllable_count(5) == 5
    assert convert_syllable_count((8, 10)) == 9
    assert convert_syllable_count(("a", "b")) == 7
    assert convert_syllable_count("bad") == 7


def test_set_from_template_tolerates_odd_tables() -> None:
    """Conversion survives short syllables/odd tables/non-dict attributes."""
    from src.templates import PoetryTemplate, _registry, register

    class _Dummy(PoetryTemplate):
        """Odd-structure template (covers tolerance branches)."""

        name = "异常结构"
        language = "fr"
        lines = 2
        syllables_per_line: ClassVar[list[int]] = [2]

        def get_syllable_constraints(self) -> Any:
            """Return a non-standard constraint table."""
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
    """AI tools set/clear the template rule description (a writing-AI prompt)."""
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
    """The draft payload includes the rule description, with a length cap."""
    draft = tools.draft_from_payload({"rule_note": "规则描述"})
    assert draft.to_payload()["rule_note"] == "规则描述"
    long_draft = tools.draft_from_payload({"rule_note": "x" * 5000})
    long_draft.normalize()
    assert len(long_draft.rule_note) == 4000


def test_set_from_template_carries_rule_note() -> None:
    """The rule description is carried by the draft during AI conversion."""

    class _WithNote(PoetryTemplate):
        """Test template with a rule description."""

        name = "带描述"
        language = "zh"
        lines = 1
        syllables_per_line: ClassVar[list[int]] = [1]
        rule_note = "注意对仗"

        def get_syllable_constraints(self) -> list[list[dict[str, Any]]]:
            """One free constraint table."""
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
    """The payload can carry structural rules; invalid ones are dropped."""
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
    """Structural rules are carried when converting a quatrain (none lost)."""
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
    """Every tool dispatch branch can be executed."""
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
    """Dispatch: read draft, unknown tool, name check before submit."""
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
# Template-editing AI agent
# --------------------------------------------------------------------------- #
def _patch_editor_llm(monkeypatch: pytest.MonkeyPatch, stub: type[Any]) -> None:
    """Replace editor_ai's LLMClient with a stub class."""
    monkeypatch.setattr(editor_ai, "LLMClient", stub)


def test_editor_no_tool_with_name_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ends when the AI answers directly and the draft already has a name."""
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
    """Reminds when no tool is called without a name; tools then finish config."""
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
    """submitted=True when the AI calls submit_template."""
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
    """An LLM exception returns an error and emits an error event."""
    stub = make_stub()

    class _Boom(stub):  # type: ignore[misc, valid-type]
        def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> Any:
            raise RuntimeError("boom")

    _patch_editor_llm(monkeypatch, _Boom)
    events: list[dict[str, Any]] = []
    agent = TemplateEditorAI({"base_url": "u", "api_key": "k", "model": "m"})
    result = agent.edit("配置", {}, emit=events.append)
    assert "failed" in result.message
    assert events[0]["type"] == "error"


def test_editor_max_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stops at the maximum round count and emits an info event."""
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
    """Non-dict tool arguments execute as an empty dict."""
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
    """Value mapping notes: normal / empty mapping / no target attribute."""
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
    """Rewrite prompt includes mapping, source code, spec, env, and rule note."""
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
    """Rewrite succeeds when the AI returns valid code."""
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
    """Retries on empty code/syntax errors until valid code arrives."""
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
    """Prompts when no tool is called, then succeeds on the next round."""
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
    """Returns an error on exceptions / never-valid code."""
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
    """EditorResult stores the result."""
    draft = tools.TemplateDraft()
    result = EditorResult(draft, True, "ok")
    assert result.draft is draft and result.submitted and result.message == "ok"


def test_editor_stub_client_unused_path() -> None:
    """StubLLMClient can be built as an editor client (interface parity)."""
    stub = StubLLMClient("u", "k", "m")
    assert stub.base_url == "u"
