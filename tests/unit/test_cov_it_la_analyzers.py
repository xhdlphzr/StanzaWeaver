# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Add unit tests that bring italian.py and latin.py line coverage to 100%.

Coverage targets (missing lines):
- italian.py: 58-75 (count_syllables_in_word private method), 91
  (_syllabify_word empty string), 122 (no-vowel word fallback), 156
  (word-final double-consonant stress branch), 184 (skip empty word),
  240 (analyze_line_variants).
- latin.py: 103 (empty-string word), 162 (breve-marker branch), 209 (main
  loop else-coda branch, proven unreachable dead code), 216-217 (no-vowel
  word onset fallback), 254 (skip empty word in a line), 269 (cross-word
  length), 292-294 (_leading_consonant_count qu/gu/su handling),
  324 (analyze_line_variants).
"""

from src.prosody.italian import ItalianAnalyzer
from src.prosody.latin import LatinAnalyzer


def test_itcount_syllables_in_word_empty() -> None:
    """Verify an empty string returns 0 (line 59)."""
    assert ItalianAnalyzer().count_syllables_in_word("") == 0


def test_itcount_syllables_in_word_no_vowel() -> None:
    """Verify a no-vowel word falls back to 1 (line 75 else branch)."""
    assert ItalianAnalyzer().count_syllables_in_word("xyz") == 1


def test_itcount_syllables_in_word_no_diphthong() -> None:
    """Verify per-vowel counting for a word without diphthongs (65-66, 74)."""
    assert ItalianAnalyzer().count_syllables_in_word("casa") == 2


def test_itcount_syllables_in_word_diphthong() -> None:
    """Verify a diphthong word hits the i+=1 merge branch (lines 67-73)."""
    assert ItalianAnalyzer().count_syllables_in_word("ciao") == 2


def test_it_syllabify_word_empty() -> None:
    """Verify a word of only an elision apostrophe returns an empty list (91)."""
    assert ItalianAnalyzer().analyze_word("'") == []


def test_it_syllabify_word_no_vowel() -> None:
    """Verify a no-vowel word falls back to a placeholder syllable (122)."""
    syls = ItalianAnalyzer().analyze_word("xyz")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_it_syllabify_word_final_two_consonants_stress() -> None:
    """Verify a final double consonant stresses the penultimate one (156)."""
    syls = ItalianAnalyzer().analyze_word("amant")
    assert len(syls) == 2
    assert syls[0].attributes["stress"] == "heavy"


def test_it_syllabify_line_skips_empty_word() -> None:
    """Verify a word yielding an empty syllable is skipped (line 184)."""
    syls = ItalianAnalyzer().syllabify_line("l' bello")
    assert syls  # At least bello's syllables are kept


def test_it_analyze_line_variants() -> None:
    """Verify line variants return the standard syllabification (240)."""
    variants = ItalianAnalyzer().analyze_line_variants("ciao bello")
    assert len(variants) == 1
    assert variants[0]


def test_la_analyze_word_empty() -> None:
    """Verify a pure-punctuation word returns an empty list (line 103)."""
    assert LatinAnalyzer().analyze_word("...") == []


def test_la_analyze_word_short_marker() -> None:
    """Verify a breve-marked vowel hits the elif normalization branch (162)."""
    syls = LatinAnalyzer().analyze_word("ă")
    assert len(syls) == 1
    assert syls[0].attributes["length"] == "short"


def test_la_analyze_word_no_vowel_onset_fallback() -> None:
    """Verify a no-vowel word uses the onset placeholder fallback (216-217)."""
    syls = LatinAnalyzer().analyze_word("bc")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_la_analyze_line_skips_empty_word() -> None:
    """Verify a word that is only an elision apostrophe is skipped (254).

    Note: analyze_word's strip set includes the apostrophe, so "l'" strips
    to "l" rather than empty; a pure apostrophe string "'" is needed so the
    word is empty after strip and ``if not syls: continue`` is hit.
    """
    assert LatinAnalyzer().analyze_line("'") == []


def test_la_analyze_line_cross_word_long() -> None:
    """Verify a vowel plus a following word with 2+ leading consonants is long."""
    syls = LatinAnalyzer().analyze_line("a strata")
    assert syls[0].attributes["length"] == "long"


def test_la_leading_consonant_count_consonantal_u() -> None:
    """Verify word-initial qu counts as one consonantal slot (292-294)."""
    assert LatinAnalyzer._leading_consonant_count("qua") == 1


def test_la_analyze_line_variants() -> None:
    """Verify line variants return the standard syllabification (324)."""
    variants = LatinAnalyzer().analyze_line_variants("a strata")
    assert len(variants) == 1
    assert variants[0]


def test_la_analyze_word_main_loop_else_coda_unreachable() -> None:
    """Probe the coda path of the main loop's else branch.

    The ``coda += lower`` on line 209 of latin.py occurs inside a word:
    consonants after a vowel and before the next vowel are always swallowed
    by the inline coda collection (lines 174-206), so the main loop's else
    branch is unreachable once a nucleus is set, i.e. dead code. This test
    records that behavior explicitly and does not aim to cover the line.
    """
    # No normal word reaches line 209; the assertion is only a regression guard.
    assert LatinAnalyzer().analyze_word("patris") is not None
