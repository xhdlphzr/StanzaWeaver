# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the Italian syllable analyzer (symbol layer)."""

from src.models.syllable import Syllable
from src.prosody.italian import ItalianAnalyzer
from src.templates.it import CanzoneTemplate


def test_count_amor() -> None:
    """Verify count_syllables for "amor"."""
    a = ItalianAnalyzer()
    # a-mor: 2 syllables, the last one stressed (consonant-final word).
    assert a.count_syllables("amor") == 2
    syls = a.analyze_word("amor")
    assert syls[-1].attributes["stress"] == "heavy"


def test_count_citta() -> None:
    """Verify count_syllables for "città"."""
    a = ItalianAnalyzer()
    # ci-ttà: 2 syllables, the last one stressed (accented final vowel).
    assert a.count_syllables("città") == 2


def test_no_sinalefe_when_prev_coda() -> None:
    """Verify no sinalefe applies when the previous word has a coda."""
    a = ItalianAnalyzer()
    # "amor" ends with the coda r, so it does not merge with the following "e".
    assert a.count_syllables("amor e") == 3


def test_sinalefe_merges_cross_word_vowels() -> None:
    """Verify sinalefe merges vowels across words."""
    a = ItalianAnalyzer()
    # The final i of "poeti" merges with the following e: 3 syllables, not 4.
    assert a.count_syllables("poeti e") == 3


def test_sinalefe_hiatus_no_merge() -> None:
    """Verify sinalefe does not merge across a hiatus."""
    a = ItalianAnalyzer()
    # Stressed final ù of "virtù" and initial e of "eterna" form a hiatus.
    assert a.count_syllables("virtù eterna") == 5


def test_sinalefe_unstressed_merges() -> None:
    """Verify sinalefe merges unstressed vowels."""
    a = ItalianAnalyzer()
    # "la" is unstressed and the initial vowel of "aria" is unstressed -> merge.
    assert a.count_syllables("la aria") == 3


def test_zio_hiatus_two_syllables() -> None:
    """Verify the "zio" hiatus yields two syllables."""
    a = ItalianAnalyzer()
    # zì-o: stressed ì and the following o form a hiatus, so 2 syllables.
    assert a.count_syllables("zìo") == 2
    syls = a.analyze_word("zìo")
    assert len(syls) == 2
    assert syls[0].attributes["stress"] == "heavy"


def _mk_line(n: int, stress_idx: int, tail: str) -> list[Syllable]:
    """Build a syllable list with the given count, stress index, and rhyme tail.

    Args:
        n: Number of syllables.
        stress_idx: Index of the stressed syllable.
        tail: Rhyme tail text.

    Returns:
        The constructed Syllable list.

    """
    syls: list[Syllable] = []
    for i in range(n):
        attrs = {
            "tone": "",
            "stress": "heavy" if i == stress_idx else "",
            "length": "",
        }
        syls.append(
            Syllable(
                nucleus=tail if i == n - 1 else "a",
                coda="",
                attributes=attrs,
            )
        )
    return syls


def _mk_canzone() -> list[list[Syllable]]:
    """Build a fully metrical canzone.

    Odd lines have 11 syllables with the 10th stressed; even lines and the
    last line have 7 syllables with the final one stressed.

    Returns:
        A list of 13 syllable lines.

    """
    lines: list[list[Syllable]] = []
    for idx in range(13):
        if idx % 2 == 0:
            # Odd line: 11 syllables, the 10th (0-based index 9) stressed.
            lines.append(_mk_line(11, 9, "a"))
        else:
            # Even line: 7 syllables, the final one (0-based index 6) stressed.
            lines.append(_mk_line(7, 6, "b"))
    # Line 13 (0-based 12) uses rhyme c so the last three lines differ.
    lines[12] = _mk_line(7, 6, "c")
    return lines


def _validate_canzone(lines: list[list[Syllable]]) -> list[str]:
    """Validate canzone.

    Args:
        lines: Syllable lines of the canzone.

    Returns:
        List of validation errors.

    """
    poem = ["x"] * 13
    return CanzoneTemplate().validate_full(poem, lines)


def test_canzone_valid_stress() -> None:
    """Verify a fully metrical canzone passes stress validation."""
    # A fully metrical canzone must not produce any stress errors.
    assert _validate_canzone(_mk_canzone()) == []


def test_canzone_odd_line_stress_on_11_fails() -> None:
    """Verify an odd line stressed on syllable 11 fails."""
    lines = _mk_canzone()
    # Make line 1 (0-based 0) stress syllable 11 instead of syllable 10.
    lines[0] = _mk_line(11, 10, "a")
    errs = _validate_canzone(lines)
    assert any("Line 1 syllable 10" in e for e in errs)
    assert any("Line 1 syllable 11" in e for e in errs)


def test_canzone_odd_line_missing_tenth_fails() -> None:
    """Verify an odd line missing the syllable-10 stress fails."""
    lines = _mk_canzone()
    # Line 1 (0-based 0) stresses syllable 6, leaving syllable 10 unstressed.
    lines[0] = _mk_line(11, 5, "a")
    errs = _validate_canzone(lines)
    assert any("Line 1 syllable 10" in e for e in errs)


def test_canzone_even_line_final_stressed() -> None:
    """Verify an even line has its final syllable stressed."""
    lines = _mk_canzone()
    # The even line (line 2, 0-based 1) already stresses its last syllable.
    errs = _validate_canzone(lines)
    assert not any("Line 2 last syllable" in e for e in errs)
    # Make the final syllable unstressed -> an error must be reported.
    lines[1] = _mk_line(7, 3, "b")
    errs = _validate_canzone(lines)
    assert any("Line 2 last syllable" in e for e in errs)
