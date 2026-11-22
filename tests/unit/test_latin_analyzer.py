# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the Latin syllable analyzer (symbol layer)."""

from src.models.syllable import Syllable
from src.prosody.latin import LatinAnalyzer
from src.templates.la import DistichonTemplate, HendecasyllabusTemplate


def _syls(lengths: list[str]) -> list[Syllable]:
    """Build a syllable list with the given lengths.

    Args:
        lengths: Length marker for each syllable.

    Returns:
        The constructed Syllable list.

    """
    return [Syllable(nucleus="a", attributes={"length": l}) for l in lengths]


def test_count_syllables_amor() -> None:
    """Verify count_syllables for "amor"."""
    a = LatinAnalyzer()
    assert a.count_syllables("amor") == 2


def test_mutua_cum_liquida_merges() -> None:
    """Verify a muta cum liquida cluster is split correctly."""
    a = LatinAnalyzer()
    # patris: pa-tris, the consonant cluster is split correctly across syllables.
    syls = a.analyze_word("patris")
    assert len(syls) == 2
    assert syls[0].onset == "p"
    assert syls[0].nucleus == "a"
    assert syls[1].onset == "tr"


def test_diphthong_is_long() -> None:
    """Verify a diphthong counts as long."""
    a = LatinAnalyzer()
    # au is a diphthong -> long.
    syls = a.analyze_word("aurum")
    assert syls[0].nucleus == "au"
    assert syls[0].attributes["length"] == "long"


def test_consonantal_u() -> None:
    """Verify consonantal u handling."""
    a = LatinAnalyzer()
    # In qu the u is consonantal and does not form a syllable of its own.
    syls = a.analyze_word("aqua")
    assert len(syls) == 2
    # The correct split is a + qua: the first syllable is "a", qu starts the second onset.
    assert syls[1].onset == "qu"


def test_leading_consonant_count() -> None:
    """Verify the leading consonant count."""
    a = LatinAnalyzer()
    # A muta cum liquida cluster counts as 1.
    assert a._leading_consonant_count("tr") == 1
    # x counts as 2 consonant positions.
    assert a._leading_consonant_count("tx") == 3
    # A plain stop counts as 1.
    assert a._leading_consonant_count("patris") == 1


def test_analyze_line_cross_word_length() -> None:
    """Verify cross-word length in analyze_line."""
    a = LatinAnalyzer()
    # arma(2) + virum(2) = 4 syllables.
    assert len(a.analyze_line("arma virum")) == 4


def test_fl_fr_not_mutacumliquida() -> None:
    """Verify fl/fr do not count as muta cum liquida."""
    a = LatinAnalyzer()
    # 'f' is a fricative, not a stop, so "fr" is not muta cum liquida;
    # a vowel followed by the two consonants f+r is long by position.
    syls = a.analyze_word("afrī")
    assert syls[0].attributes["length"] == "long"


def test_fuimus_three_syllables() -> None:
    """Verify "fuimus" has three syllables."""
    a = LatinAnalyzer()
    # "ui" is not a diphthong, so it splits into u+i -> fu-i-mus, 3 syllables.
    assert len(a.analyze_word("fuimus")) == 3


def test_macron_diphthong_ae() -> None:
    """Verify a macronized "ae" is still a long diphthong."""
    a = LatinAnalyzer()
    # Even with a macron, "āe" is recognized as the diphthong ae and is long.
    syls = a.analyze_word("āe")
    assert len(syls) == 1
    assert syls[0].nucleus == "ae"
    assert syls[0].attributes["length"] == "long"


def test_elision_reduces_syllables() -> None:
    """Verify elision reduces the syllable count."""
    a = LatinAnalyzer()
    # "vita" ends in the vowel a and "est" begins with the vowel e -> elision.
    # Normally vi-ta-est = 3; after elision vi-test = 2.
    assert len(a.analyze_line("vita est")) == 2


def test_hendecasyllabic_syllable5_long() -> None:
    """Verify the hendecasyllable requires syllable 5 to be long."""
    t = HendecasyllabusTemplate()
    # Constraint table row 5 (index 4) must be long.
    cons = t.get_syllable_constraints()
    assert cons[0][4]["attributes"]["length"] == "long"
    # Build 11 syllables with syllable 5 short -> validate_full must report it.
    lengths = [
        "long",
        "short",
        "long",
        "short",
        "short",
        "long",
        "short",
        "long",
        "short",
        "long",
        "short",
    ]
    errs = t.validate_full(["parulapara"], [_syls(lengths)])
    assert any("Syllable 5" in e for e in errs)


def test_distichon_pentameter_caesura() -> None:
    """Verify the distichon pentameter caesura."""
    t = DistichonTemplate()
    # The last 6 syllables must be long short short long short short.
    tail = ["long", "short", "short", "long", "short", "short"]
    pent = _syls(["long", "short", "short", "long", "short"] + tail)  # 11 syllables

    # Good: there is a word boundary after the first 5 syllables (before the last 6).
    good_poem = ["", "parulapara parulaparapa"]
    errs_good = t.validate_full(good_poem, [[], pent])
    assert not any("caesura" in e for e in errs_good)

    # Bad: the line is a single 11-syllable word, so there is no word boundary.
    bad_poem = ["", "aaaaaaaaaaa"]
    errs_bad = t.validate_full(bad_poem, [[], pent])
    assert any("caesura" in e for e in errs_bad)
