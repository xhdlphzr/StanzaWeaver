# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the Chinese syllable analyzer (symbol layer)."""

from typing import Any

from src.models.syllable import Syllable
from src.prosody.chinese import ChineseAnalyzer
from src.templates.zh import QijueTemplate, WujueTemplate


def _mk_line(pairs: list[tuple[str, str]]) -> list[Syllable]:
    """Build one line of Syllables from a list of (tone, final) pairs.

    Args:
        pairs: Each element is (tone, final); final is used directly as the
            nucleus (no coda).

    Returns:
        List of Syllables.

    """
    return [
        Syllable(
            onset="",
            nucleus=final,
            coda="",
            attributes={"tone": tone, "stress": "", "length": ""},
        )
        for tone, final in pairs
    ]


def test_count_syllables_counts_cjk_chars() -> None:
    """Verify count_syllables counts CJK characters."""
    a = ChineseAnalyzer()
    assert a.count_syllables("床前明月光") == 5
    assert a.count_syllables("  静夜思  ") == 3
    assert a.count_syllables("") == 0


def test_analyze_word_single_char_parts() -> None:
    """Verify analyze_word handles single-character parts."""
    a = ChineseAnalyzer()
    # guāng: onset g, nucleus a, coda ng, first tone (level)
    syls = a.analyze_word("光")
    assert len(syls) == 1
    s = syls[0]
    assert s.onset == "g"
    assert s.nucleus == "ua"
    assert s.coda == "ng"
    assert s.attributes["tone"] == "平"


def test_analyze_word_tone_ping_ze() -> None:
    """Verify analyze_word maps tones to ping/ze."""
    a = ChineseAnalyzer()
    # qù (4th tone) -> oblique
    assert a.analyze_word("去")[0].attributes["tone"] == "仄"
    # chuáng (2nd tone) -> level
    assert a.analyze_word("床")[0].attributes["tone"] == "平"


def test_tokenize_line_keeps_only_cjk() -> None:
    """Verify tokenize_line keeps only CJK characters."""
    a = ChineseAnalyzer()
    assert a.tokenize_line("床前，明月光！") == ["床", "前", "明", "月", "光"]


def test_analyze_word_variants_polyphonic() -> None:
    """Verify analyze_word_variants returns polyphonic variants."""
    a = ChineseAnalyzer()
    # zhōng (level) / zhòng (oblique): polyphonic character
    variants = a.analyze_word_variants("中")
    tones = {s.attributes["tone"] for v in variants for s in v}
    assert "平" in tones
    assert "仄" in tones
    # Returns whole-word readings; each item is the word's Syllable sequence
    assert all(isinstance(v, list) for v in variants)
    assert all(len(v) == 1 for v in variants)


def test_neutral_tone_maps_to_ping() -> None:
    """Verify the neutral tone maps to ping."""
    a = ChineseAnalyzer()
    # de is a neutral tone and should map to level
    assert a.analyze_word("的")[0].attributes["tone"] == "平"


def test_heteronym_no_invalid_mix() -> None:
    """Verify polyphonic chars keep only real readings.

    No illegal onset/nucleus mixed readings are produced.
    """
    a = ChineseAnalyzer()
    variants = a.analyze_word_variants("长")
    readings = {
        (s.onset, s.nucleus, s.coda, s.attributes["tone"]) for v in variants for s in v
    }
    # zhǎng (oblique) / cháng (level): only two real readings
    assert readings == {("zh", "a", "ng", "仄"), ("ch", "a", "ng", "平")}


def test_heteronym_no_false_accept_in_meter() -> None:
    """Do not accept non-existent onset+tone readings as metrically valid.

    Regression: a character with onset zh and level tone.
    """
    from src.prosody.meter_validator import MeterValidator
    from src.templates import _make_syl

    tpl: dict[str, Any] = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [1],
        "syllable_constraints": [[_make_syl(onset="zh", attributes={"tone": "平"})]],
    }
    result = MeterValidator().validate_line("长", 0, tpl)
    assert result.passed is False


def test_sanpingwei_flagged_sanzewei_removed() -> None:
    """Verify three-level tails are flagged and three-oblique tails removed."""
    tpl = WujueTemplate()
    # Line 2 ends with three level tones; it should be flagged
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("平", "ang")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ang")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("Three level-tone tail" in e for e in errors)
    # Three-oblique tails are no longer forbidden and should not be reported
    assert not any("three-oblique-tone tail" in e for e in errors)


def test_sanzewei_no_longer_error() -> None:
    """Verify three-oblique tails are no longer reported as errors."""
    tpl = WujueTemplate()
    # A valid five-character quatrain ending in three oblique tones must not report it
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "ang")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ang")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert not any("three-oblique-tone tail" in e for e in errors)
    # The poem is fully compliant (no other errors)
    assert errors == []


def test_guping_still_reported() -> None:
    """Verify isolated-level violations are still reported."""
    tpl = QijueTemplate()
    # Isolated-level check stays: line 4 has only the rhyme foot level, so report it
    poem = ["", "", "", ""]
    syllables = [
        _mk_line(
            [
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "ang"),
            ]
        ),
        _mk_line(
            [
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "ang"),
            ]
        ),
        _mk_line(
            [
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
            ]
        ),
        _mk_line(
            [
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "ang"),
            ]
        ),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("Isolated level" in e for e in errors)


def test_rhyme_tongyun_ing_ong_fail() -> None:
    """Verify ing and ong belong to different rhyme groups."""
    tpl = WujueTemplate()
    # ing and ong are in different rhyme groups, so they should not rhyme
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "ing")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ong")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert errors, "ing (庚) and ong (东) do not share a rhyme group"


def test_rhyme_tongyun_i_u_fail() -> None:
    """Verify i and u belong to different rhyme groups."""
    tpl = WujueTemplate()
    # i and u are in different rhyme groups, so they should not rhyme
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "i")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "u")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("Rhyme (lines 2 and 4)" in e for e in errors)
