# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Fill line-coverage gaps in the Chinese syllable analyzer."""

from unittest.mock import patch

from pypinyin import Style

from src.models.syllable import Syllable
from src.prosody.chinese import (
    ChineseAnalyzer,
    _split_final,
    _tone_to_pingze,
)


def test_split_final_empty_returns_empty_pair() -> None:
    """Verify _split_final returns ("", "") for empty input."""
    assert _split_final("") == ("", "")


def test_tone_to_pingze_empty_returns_ping() -> None:
    """Verify _tone_to_pingze maps an empty string to ping."""
    assert _tone_to_pingze("") == "平"


def test_tone_to_pingze_unusual_digit_returns_ping() -> None:
    """Verify _tone_to_pingze maps unusual digits (e.g. tone 5) to ping."""
    assert _tone_to_pingze("iao5") == "平"
    assert _tone_to_pingze("x5") == "平"


def test_analyze_word_empty_returns_empty() -> None:
    """Verify analyze_word returns an empty list for empty input (line 173)."""
    a = ChineseAnalyzer()
    assert a.analyze_word("") == []


def test_analyze_word_variants_empty_returns_empty() -> None:
    """Verify analyze_word_variants returns empty for empty input (line 191)."""
    a = ChineseAnalyzer()
    assert a.analyze_word_variants("") == []


def test_analyze_word_variants_fallback_empty_char_syls() -> None:
    """Verify a char with no candidate readings gets an empty Syllable (239).

    Mock pinyin so a char's finals candidates are empty; the inner double
    loop yields no Syllable and the ``if not char_syls`` fallback runs.
    """
    a = ChineseAnalyzer()
    initials_list: list[list[str]] = [["x"]]
    finals_list: list[list[str]] = [[]]

    def _pinyin(
        word: str,
        style: Style = Style.NORMAL,
        strict: bool = True,
        heteronym: bool = False,
    ) -> list[list[str]]:
        """Return preset initials/finals lists for the mock pinyin by style."""
        if style == Style.INITIALS:
            return initials_list
        return finals_list

    with patch("src.prosody.chinese.pinyin", side_effect=_pinyin):
        variants = a.analyze_word_variants("中")
    # The fallback added one empty Syllable, so one reading is produced
    assert len(variants) == 1
    assert variants[0][0].nucleus == ""


def test_analyze_word_variants_truncates_to_64() -> None:
    """Verify the Cartesian product truncates in order past 64 (line 253).

    Mock pinyin so one char yields 65 candidate readings (distinct
    nuclei), triggering ``if len(result) > 64`` and keeping the first 64.
    """
    a = ChineseAnalyzer()
    finals: list[str] = [f"{i}1" for i in range(65)]
    initials_list: list[list[str]] = [["x"]]
    finals_list: list[list[str]] = [finals]

    def _pinyin(
        word: str,
        style: Style = Style.NORMAL,
        strict: bool = True,
        heteronym: bool = False,
    ) -> list[list[str]]:
        """Return preset initials/finals lists for the mock pinyin by style."""
        if style == Style.INITIALS:
            return initials_list
        return finals_list

    with patch("src.prosody.chinese.pinyin", side_effect=_pinyin):
        variants = a.analyze_word_variants("中")
    assert len(variants) == 64


def test_analyze_line_variants_empty_word_variant() -> None:
    """Verify an empty word reading falls back to [[]] (line 278).

    Mock ``analyze_word_variants`` to return an empty list so the
    per-char loop takes the ``if not wv: wv = [[]]`` branch.
    """
    a = ChineseAnalyzer()
    with patch.object(ChineseAnalyzer, "analyze_word_variants", return_value=[]):
        variants = a.analyze_line_variants("中")
    # The [[]] fallback times the initial [[]] is still [[]]
    assert variants == [[]]


def test_analyze_word_variants_mismatched_lengths_fallback() -> None:
    """Verify zip pairing when initial/final counts differ (line 294)."""
    a = ChineseAnalyzer()
    initials_list: list[list[str]] = [["x", "y"]]
    finals_list: list[list[str]] = [["a1", "b1", "c1"]]

    def _pinyin(
        word: str,
        style: Style = Style.NORMAL,
        strict: bool = True,
        heteronym: bool = False,
    ) -> list[list[str]]:
        """Return preset initials/finals lists for the mock pinyin by style."""
        if style == Style.INITIALS:
            return initials_list
        return finals_list

    with patch("src.prosody.chinese.pinyin", side_effect=_pinyin):
        variants = a.analyze_word_variants("中")
    # zip truncates to the shorter one -> 2 readings
    assert len(variants) == 2


def test_analyze_line_variants_truncates_to_64() -> None:
    """Verify line reading combos over 64 keep the first 64 (line 294)."""
    a = ChineseAnalyzer()
    many = [
        [Syllable(onset="", nucleus="a", coda="", attributes={})] for _ in range(10)
    ]
    with patch.object(ChineseAnalyzer, "analyze_word_variants", return_value=many):
        variants = a.analyze_line_variants("中中")
    assert len(variants) == 64
