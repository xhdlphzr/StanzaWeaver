# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the data-driven structural rules.

Cover rule-data validation and the regulated-verse error branches, and check
parity with the built-in quatrain/regulated-verse template validation so
data-driven carrying does not change the verdict.
"""

from typing import Any

import pytest

from src.models.syllable import Syllable
from src.prosody.syllable_counter import get_analyzer
from src.templates import _registry, get
from src.templates import structural as st
from src.templates.zh import register_chinese_templates

WUJUE_RULES: dict[str, Any] = {
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


def _syl(tone: str, nucleus: str = "a", coda: str = "") -> Syllable:
    """Build a syllable with tone and nucleus."""
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": tone, "stress": "", "length": ""},
    )


def _line(tones: str, nuclei: str | None = None) -> list[Syllable]:
    """Build one line of syllables from a tone string (nucleus optional)."""
    nucleus_list = list(nuclei) if nuclei else ["a"] * len(tones)
    return [_syl(tone, nucleus_list[i]) for i, tone in enumerate(tones)]


def _line_last(tones: str, last_nucleus: str) -> list[Syllable]:
    """Build a line and set the last syllable's nucleus (for rhyme checks)."""
    line = _line(tones)
    line[-1] = _syl(tones[-1], last_nucleus)
    return line


def _poem(*tone_lines: str) -> tuple[list[str], list[list[Syllable]]]:
    """Build poem texts and syllables (texts are placeholders for rhyme keys)."""
    poem = [f"line{i}" for i in range(len(tone_lines))]
    return poem, [_line(tones) for tones in tone_lines]


# --------------------------------------------------------------------------- #
# Rule data validation
# --------------------------------------------------------------------------- #
def test_normalize_structural_rules_none() -> None:
    """None means there are no structural rules."""
    assert st.normalize_structural_rules(None) == (None, None)


def test_normalize_structural_rules_errors() -> None:
    """Invalid rule data returns an error."""
    assert st.normalize_structural_rules("bad")[1] is not None
    _, unknown_kind_error = st.normalize_structural_rules({"kind": "x"})
    assert unknown_kind_error is not None
    assert "Unknown structural rule kind" in unknown_kind_error
    assert (
        st.normalize_structural_rules({"kind": "jinti"})[1]
        == "Structural rules are missing attribute/level_value/oblique_value"
    )
    assert (
        st.normalize_structural_rules(
            {
                "kind": "jinti",
                "attribute": "tone",
                "level_value": "平",
                "oblique_value": "仄",
                "rhyme_lines": [1],
            }
        )[1]
        == "Structural rules are missing positions/rhyme_lines"
    )
    assert (
        st.normalize_structural_rules(
            {
                "kind": "jinti",
                "attribute": "tone",
                "level_value": "平",
                "oblique_value": "仄",
                "positions": [-1],
                "rhyme_lines": [1],
            }
        )[1]
        is not None
    )


def test_normalize_structural_rules_success() -> None:
    """Valid rules are normalized (booleans coerced, lists copied)."""
    raw = {
        "kind": "jinti",
        "attribute": "tone",
        "level_value": "平",
        "oblique_value": "仄",
        "positions": (1, 3),
        "rhyme_lines": [1, 3],
        "optional_first_rhyme": 1,
        "forbid_sanpingwei": 0,
    }
    rules, error = st.normalize_structural_rules(raw)
    assert error is None
    assert rules is not None
    assert rules["positions"] == [1, 3]
    assert rules["optional_first_rhyme"] is True
    assert rules["forbid_sanpingwei"] is False
    assert rules["forbid_guping"] is False


def test_as_int_list_invalid_item() -> None:
    """An int list with an invalid item returns None."""
    assert st._as_int_list(["a"]) is None
    assert st._as_int_list("x") is None


# --------------------------------------------------------------------------- #
# Regulated-verse rule branches
# --------------------------------------------------------------------------- #
def test_check_short_poem_returns_empty() -> None:
    """Too few lines returns immediately."""
    assert st.check_jinti_rules("zh", ["a"], [_line("平")], WUJUE_RULES) == []


def test_check_skips_empty_lines_and_short_first_line() -> None:
    """Empty lines are skipped; fixed positions beyond line 1 are filtered."""
    rules = dict(WUJUE_RULES)
    poem = ["a", "b", "c", "d"]
    syllables = [[], _line("平"), [_syl("平")], _line("平")]
    errors = st.check_jinti_rules("zh", poem, syllables, rules)
    assert isinstance(errors, list)


def test_last_value_empty_line() -> None:
    """An empty line's last-syllable attribute is an empty string."""
    assert st._last_value([], "tone") == ""


def test_check_skips_empty_rhyme_line() -> None:
    """Skip the rhyme check for a rhyme line with no syllables."""
    poem = ["a", "b", "c", "d"]
    syllables = [
        _line("仄仄平平仄"),
        [],
        _line("平平平仄仄"),
        _line("仄仄仄平平"),
    ]
    errors = st.check_jinti_rules("zh", poem, syllables, WUJUE_RULES)
    assert isinstance(errors, list)


def test_check_sanpingwei_and_guping() -> None:
    """Both three-level tails and isolated levels are detected."""
    # Line 1 ends in three level tones -> three-level tail.
    # Line 2 has a level foot with only one level tone -> isolated level.
    poem, syllables = _poem("仄平平平", "仄仄仄平", "平平平平", "仄仄仄平")
    errors = st.check_jinti_rules("zh", poem, syllables, WUJUE_RULES)
    assert any("three level-tone tail" in e for e in errors)
    assert any("isolated level" in e for e in errors)


def test_check_structure_and_rhyme_errors() -> None:
    """Detect leading/responding feet, alternation, opposition, adhesion, rhyme."""
    # Line 3 (leading) has a level foot; line 4 (responding) has an oblique foot
    poem1, syl1 = _poem("仄仄平平仄", "平平仄仄平", "平平仄仄平", "仄仄平平仄")
    errors1 = st.check_jinti_rules("zh", poem1, syl1, WUJUE_RULES)
    assert any("leading line" in e for e in errors1)
    assert any("responding line" in e for e in errors1)

    # Fixed-position alternation broken: line 1 positions 2 and 4 are both level
    poem2, syl2 = _poem("平平平平仄", "平平仄仄平", "平平平仄仄", "仄仄仄平平")
    errors2 = st.check_jinti_rules("zh", poem2, syl2, WUJUE_RULES)
    assert any("should alternate" in e for e in errors2)

    # In-couplet opposition broken: lines 1 and 2 both have level at position 2
    poem3, syl3 = _poem("平平平仄仄", "平平仄仄平", "仄仄平平仄", "仄仄仄平平")
    errors3 = st.check_jinti_rules("zh", poem3, syl3, WUJUE_RULES)
    assert any("should oppose" in e for e in errors3)

    # Cross-couplet adhesion broken: line 2 position 2 is level,
    # line 3 position 2 is oblique.
    poem4, syl4 = _poem("仄仄平平仄", "平平仄仄平", "仄仄平平仄", "仄仄仄平平")
    errors4 = st.check_jinti_rules("zh", poem4, syl4, WUJUE_RULES)
    assert any("should adhere" in e for e in errors4)


def test_check_rhyme_tone_and_mismatch() -> None:
    """Non-level rhyme feet error; a rhymed first line must match even lines."""
    # Line 2's rhyme foot is oblique
    poem1, syl1 = _poem("仄仄平平仄", "平平仄仄仄", "平平平仄仄", "仄仄仄平平")
    errors1 = st.check_jinti_rules("zh", poem1, syl1, WUJUE_RULES)
    assert any("rhyme should be '平'" in e for e in errors1)

    # First line rhymes but its nucleus differs from lines 2 and 4
    poem2 = ["a", "b", "c", "d"]
    syllables2 = [
        _line_last("平平仄仄平", "an"),
        _line_last("平平仄仄平", "en"),
        _line_last("平平平仄仄", "an"),
        _line_last("仄仄仄平平", "en"),
    ]
    errors2 = st.check_jinti_rules("zh", poem2, syllables2, WUJUE_RULES)
    assert any("Rhyme mismatch" in e for e in errors2)

    # First line has a level foot and rhymes -> rhyme check passes
    syllables3 = [
        _line_last("平平仄仄平", "an"),
        _line_last("平平仄仄平", "an"),
        _line_last("平平平仄仄", "an"),
        _line_last("仄仄仄平平", "an"),
    ]
    errors3 = st.check_jinti_rules(
        "zh",
        poem2,
        syllables3,
        {**WUJUE_RULES, "forbid_sanpingwei": False, "forbid_guping": False},
    )
    assert not any("Rhyme mismatch" in e for e in errors3)


def test_check_unknown_values_are_skipped() -> None:
    """Unknown attribute values skip alternation/opposition/adhesion checks."""
    poem = ["a", "b", "c", "d"]
    syllables = [[_syl("")] for _ in range(4)]
    errors = st.check_jinti_rules(
        "zh",
        poem,
        syllables,
        {**WUJUE_RULES, "forbid_sanpingwei": True, "forbid_guping": True},
    )
    # Empty attributes cause no tail, isolated-level or structure errors,
    # but the rhyme check still fails because no level tone is present.
    assert errors
    assert all("rhyme should be" in e for e in errors)


# --------------------------------------------------------------------------- #
# Parity with the built-in templates
# --------------------------------------------------------------------------- #
POEMS: list[list[str]] = [
    ["远岫依烟岭", "溪流伴月明", "桃红迷柳岸", "古道远山风"],
    ["仄仄平平仄", "平平仄仄平", "平平平仄仄", "仄仄仄平平"],
    ["春江花月风", "秋山夜雪月", "野渡无人灯", "寒梅独映雪"],
    ["国破山河在", "城春草木深", "感时花溅泪", "恨别鸟惊心"],
    ["空山新雨后", "天气晚来秋", "明月松间照", "清泉石上流"],
    ["黄河远上白云间", "一片孤城万仞山", "羌笛何须怨杨柳", "春风不度玉门关"],
]


@pytest.mark.parametrize("key", ["zh_wujue", "zh_qijue"])
def test_parity_with_builtin_short_forms(key: str) -> None:
    """Data-driven rules match the built-in quatrain templates."""
    register_chinese_templates()
    template = get(key)
    analyzer = get_analyzer("zh")
    rules = st.normalize_structural_rules(template.structural_rules)[0]
    assert rules is not None
    for poem in POEMS:
        expected = 5 if key == "zh_wujue" else 7
        if any(len(line) != expected for line in poem):
            continue
        syllables = [analyzer.analyze_line_variants(line)[0] for line in poem]
        builtin = template.validate_full(poem, syllables)
        dataized = st.check_jinti_rules("zh", poem, syllables, rules)
        assert (not builtin) == (not dataized), (poem, builtin, dataized)


@pytest.mark.parametrize("key", ["zh_wulv", "zh_qilv"])
def test_parity_with_builtin_regular_forms(key: str) -> None:
    """Data-driven rules match built-in regulated verse on rhyme/tail checks."""
    register_chinese_templates()
    template = get(key)
    rules = st.normalize_structural_rules(template.structural_rules)[0]
    assert rules is not None
    assert rules["rhyme_lines"] == [1, 3, 5, 7]
    analyzer = get_analyzer("zh")
    poem = [
        "空山新雨后",
        "天气晚来秋",
        "明月松间照",
        "清泉石上流",
        "竹喧归浣女",
        "莲动下渔舟",
        "随意春芳歇",
        "王孙自可留",
    ]
    syllables = [analyzer.analyze_line_variants(line)[0] for line in poem]
    builtin = template.validate_full(poem, syllables)
    dataized = st.check_jinti_rules("zh", poem, syllables, rules)
    assert (not builtin) == (not dataized), (builtin, dataized)


def test_structural_rules_registered_for_jinti_templates() -> None:
    """Quatrain and regulated-verse templates declare structural rules."""
    register_chinese_templates()
    for key, lines, positions in [
        ("zh_wujue", 4, [1, 3]),
        ("zh_qijue", 4, [1, 3, 5]),
        ("zh_wulv", 8, [1, 3]),
        ("zh_qilv", 8, [1, 3, 5]),
    ]:
        template = get(key)
        rules, error = st.normalize_structural_rules(template.structural_rules)
        assert error is None and rules is not None
        assert template.lines == lines
        assert rules["positions"] == positions


def test_special_rules_are_strings() -> None:
    """Built-in templates expose special_rules as tuples of strings."""
    for template in _registry.values():
        assert isinstance(template.special_rules, tuple)
        assert all(isinstance(rule, str) for rule in template.special_rules)
