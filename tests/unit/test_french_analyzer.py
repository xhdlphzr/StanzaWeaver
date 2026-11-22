# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the French syllable analyzer (symbol layer)."""

from src.prosody.french import FrenchAnalyzer
from src.templates.fr import RondeauTemplate


def test_count_syllables_parle() -> None:
    """Verify count_syllables for "parle"."""
    a = FrenchAnalyzer()
    # par-le: the final mute e is dropped -> 1 syllable.
    assert a.count_syllables("parle") == 1


def test_rhyme_key_parle() -> None:
    """Verify rhyme_key for "parle"."""
    a = FrenchAnalyzer()
    # Once the final mute e is dropped, the rhyme tail is the last vowel nucleus a.
    assert a.rhyme_key("parle") == "a"


def test_count_syllables_bonjour() -> None:
    """Verify count_syllables for "bonjour"."""
    a = FrenchAnalyzer()
    # bon-jour: 2 syllables.
    assert a.count_syllables("bonjour") == 2


def test_digraph_eau() -> None:
    """Verify the "eau" digraph is one nucleus."""
    a = FrenchAnalyzer()
    syls = a.analyze_word("eau")
    assert len(syls) == 1
    assert syls[0].nucleus == "eau"


def test_single_nucleus_words() -> None:
    """Verify words with a single nucleus count as one syllable."""
    a = FrenchAnalyzer()
    # FR-1: triphthongs and diphthongs are treated as a single nucleus.
    assert a.count_syllables("oui") == 1
    assert a.count_syllables("bien") == 1
    assert a.count_syllables("viens") == 1
    assert a.count_syllables("yeux") == 1
    assert a.analyze_word("oui")[0].nucleus == "oui"
    assert a.analyze_word("bien")[0].nucleus == "ien"
    assert a.analyze_word("viens")[0].nucleus == "ien"
    assert a.analyze_word("yeux")[0].nucleus == "yeu"


def test_final_mute_e_silent() -> None:
    """Verify a final mute e is silent."""
    a = FrenchAnalyzer()
    # Final mute e is dropped (standard French): entre/table/porte/parle = 1 syllable.
    assert a.count_syllables("entre") == 1
    assert a.count_syllables("table") == 1
    assert a.count_syllables("porte") == 1
    assert a.count_syllables("parle") == 1
    # Count normally when the final vowel is not e, or e has no other vowel nucleus before it.
    assert a.count_syllables("maison") == 2
    assert a.count_syllables("petite") == 2
    assert a.count_syllables("le") == 1
    assert a.count_syllables("que") == 1


def test_rhyme_key_nasal_merge() -> None:
    """Verify nasal vowels merge in rhyme keys."""
    a = FrenchAnalyzer()
    # FR-3: nasal vowels are merged and final silent consonants are dropped.
    assert a.rhyme_key("an") == a.rhyme_key("en")
    assert a.rhyme_key("mai") == a.rhyme_key("mais")
    assert a.rhyme_key("lit") == a.rhyme_key("li")
    assert a.rhyme_key("ami") == a.rhyme_key("amis")


def test_syllabify_line_no_cross_word_elision() -> None:
    """Verify syllabify_line does not elide across words."""
    a = FrenchAnalyzer()
    # An apostrophe elision still counts as 1 syllable (l'eau is one word form).
    assert a.count_syllables("l'eau") == 1
    # Vowels meeting across word boundaries are not elided: la + eau = 2 syllables.
    assert a.count_syllables("la eau") == 2


def test_rondeau_accepts_uniform_10() -> None:
    """Verify a rondeau accepts a uniform line length of 10."""
    from src.prosody.meter_validator import MeterValidator

    template = RondeauTemplate()
    # Each line has 10 "la" (1 syllable each), for 15 lines total.
    line = " ".join(["la"] * 10)
    poem = [line for _ in range(15)]
    validator = MeterValidator()
    result = validator.validate_count_only(poem, template.to_dict())
    assert not result.errors
    # The range should allow 8 or 10 syllables.
    assert template.syllables_per_line[0] == (8, 10)
