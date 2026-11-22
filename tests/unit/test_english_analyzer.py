# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the English syllable analyzer (symbol layer, offline CMUdict seeding)."""

from unittest import mock

from src.prosody.english import EnglishAnalyzer


def test_parse_phones_single_syllable() -> None:
    """Verify _parse_phones for a single-syllable word."""
    a = EnglishAnalyzer()
    # test /tɛst/: onset t, nucleus ɛ, coda st, with primary stress.
    syls = a._parse_phones(["T", "EH1", "S", "T"])
    assert len(syls) == 1
    s = syls[0]
    assert s.onset == "T"
    assert s.nucleus == "EH"
    assert s.coda == "ST"
    assert s.attributes["stress"] == "heavy"


def test_parse_phones_two_syllables() -> None:
    """Verify _parse_phones for a two-syllable word."""
    a = EnglishAnalyzer()
    # happy /hæpi/: first syllable stressed, second light.
    syls = a._parse_phones(["HH", "AE1", "P", "IY0"])
    assert len(syls) == 2
    assert syls[0].onset == "HH"
    assert syls[0].nucleus == "AE"
    assert syls[0].coda == "P"
    assert syls[0].attributes["stress"] == "heavy"
    assert syls[1].nucleus == "IY"
    assert syls[1].attributes["stress"] == "light"


def test_analyze_word_seeded() -> None:
    """Verify analyze_word for a seeded word."""
    a = EnglishAnalyzer()
    syls = a.analyze_word("light")
    assert len(syls) == 1
    assert syls[0].nucleus == "AY"
    assert syls[0].attributes["stress"] == "heavy"


def test_fallback_analyze_unknown_word() -> None:
    """Verify the fallback analysis for an unknown word."""
    a = EnglishAnalyzer()
    syls = a._fallback_analyze("rhythm")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"
    assert syls[0].attributes["stress"] == "light"


def test_rhyme_tail_seeded() -> None:
    """Verify rhyme_tail for a seeded word."""
    a = EnglishAnalyzer()
    assert a.rhyme_tail("light") == "AY1 T"
    # An unknown word has no pronunciation, so it cannot serve as a rhyme key.
    assert a.rhyme_tail("zzznotaword") is None


def test_count_syllables_offline() -> None:
    """Verify count_syllables falls back offline (no real lexicon / cmudict).

    Force pronunciation lookups to return nothing so the analyzer uses its
    heuristic fallback, making the result purely regex-determined:
    "rhythm" (y counts 1) + "xyz" (y counts 1) = 2.
    """
    a = EnglishAnalyzer()
    with mock.patch.object(EnglishAnalyzer, "_get_pronunciations", return_value=[]):
        assert a.count_syllables("rhythm xyz") == 2
