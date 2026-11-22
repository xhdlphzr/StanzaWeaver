# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Coverage tests for the English and French syllable analyzers.

This file changes no existing test; it only adds unit tests for uncovered
branches in `src/prosody/english.py` and `src/prosody/french.py`:

- English: lazy CMUdict loader, local vocabulary fallback, 64-combo cap,
  vowel-less phoneme strings, adjacent-vowel skipping, consonant-cluster
  merging, unknown word with no vowel fallback.
- French: empty word, nasal back-vowel merge, placeholder-nucleus rhyme,
  word syllable count, empty syllable skipping, liaison, line variants.
"""

from unittest import mock

import nltk  # type: ignore[import-untyped]

from src.knowledge import vocabulary
from src.prosody import english as english_module
from src.prosody.english import EnglishAnalyzer
from src.prosody.french import FrenchAnalyzer


def test_load_cmudict_body_executes() -> None:
    """Verify the `_load_cmudict` body really runs in this session.

    Cover lines 63-64, 66-67, 70, 72, 74. Inject the mock directly into
    ``nltk.corpus.__dict__`` instead of ``sys.modules["nltk.corpus"]``'s
    ``cmudict`` attribute: ``nltk.corpus`` is a LazyModule proxy and is not
    the ``sys.modules`` entity resolved by import, so only the latter
    intercepts the inner ``from nltk.corpus import cmudict``. Force
    ``nltk.data.find`` to raise LookupError to hit the except download
    branch (lines 68-69), then restore global state afterwards.
    """
    import importlib
    import sys

    importlib.import_module(
        "nltk.corpus"
    )  # Ensure a real module exists in sys.modules so injection cannot miss

    gl = english_module._load_cmudict.__globals__
    saved_loaded = gl["_cmudict_loaded"]
    saved_cache = gl["_ARPABET_TO_PHONEMES"]
    real_corpus = sys.modules["nltk.corpus"]
    saved_cmu = real_corpus.__dict__.get("cmudict")

    gl["_cmudict_loaded"] = False
    gl["_ARPABET_TO_PHONEMES"] = {}

    fake_dict: dict[str, list[list[str]]] = {"foobar": [["F", "OW1", "B", "AA1", "R"]]}
    mock_cmu = mock.MagicMock()
    mock_cmu.dict.return_value = fake_dict
    try:
        real_corpus.__dict__["cmudict"] = mock_cmu
        with (
            mock.patch.object(nltk.data, "find", side_effect=LookupError),
            mock.patch.object(nltk, "download", return_value=None),
        ):
            english_module._load_cmudict()
        assert gl["_cmudict_loaded"] is True
        assert "foobar" in gl["_ARPABET_TO_PHONEMES"]
    finally:
        if saved_cmu is None:
            real_corpus.__dict__.pop("cmudict", None)
        else:
            real_corpus.__dict__["cmudict"] = saved_cmu
        # Restore global state so existing tests are unaffected
        gl["_cmudict_loaded"] = saved_loaded
        gl["_ARPABET_TO_PHONEMES"] = saved_cache


def test_load_cmudict_inner_guard_return() -> None:
    """Verify the double-checked lock's inner guard returns early (line 65).

    Replace `_cmudict_lock`'s `__enter__` so it sets `_cmudict_loaded` to
    True at the moment the lock is taken, hitting the inner
    `if _cmudict_loaded: return`.
    """
    saved_loaded = english_module._cmudict_loaded
    saved_lock = english_module._cmudict_lock

    english_module._cmudict_loaded = False
    fake_lock = mock.MagicMock()

    def _lock_enter(self: object) -> mock.MagicMock:
        """Mark cmudict as loaded on lock entry and return the lock object."""
        english_module._cmudict_loaded = True
        return fake_lock

    fake_lock.__enter__ = _lock_enter
    fake_lock.__exit__ = mock.Mock(return_value=False)
    english_module._cmudict_lock = fake_lock

    english_module._load_cmudict()

    # The inner guard returns early, so the loader body never runs
    assert english_module._cmudict_loaded is True
    # Restore global state so existing tests are unaffected
    english_module._cmudict_loaded = saved_loaded
    english_module._cmudict_lock = saved_lock


def test_get_pronunciations_returns_db_prons() -> None:
    """Verify a local vocabulary hit returns directly (line 99)."""
    analyzer = EnglishAnalyzer()
    prons: list[list[str]] = [["B", "AH1", "R"]]
    with mock.patch.object(vocabulary, "get_en_pron", return_value=prons):
        result = analyzer._get_pronunciations("bar")
    assert result == prons


def test_analyze_line_variants_combo_cap() -> None:
    """Verify the 64-combo cap on polyphonic variants (lines 193, 195).

    Each word has 4 pronunciations; 4 words multiply far past 64, so both
    the inner and outer break triggers.
    """
    analyzer = EnglishAnalyzer()
    four_prons: list[list[str]] = [
        ["B", "AH1"],
        ["K", "AH1"],
        ["D", "AH1"],
        ["F", "AH1"],
    ]
    with mock.patch.object(vocabulary, "get_en_pron", return_value=four_prons):
        combos = analyzer.analyze_line_variants("w1 w2 w3 w4")
    assert len(combos) <= 64
    assert len(combos) == 64


def test_parse_phones_no_vowels() -> None:
    """Verify a vowel-less phoneme string returns an empty list (line 217)."""
    analyzer = EnglishAnalyzer()
    assert analyzer._parse_phones(["B", "T"]) == []


def test_parse_phones_adjacent_vowels_skip() -> None:
    """Verify adjacent vowels with no consonant skip the empty onset (230)."""
    analyzer = EnglishAnalyzer()
    syls = analyzer._parse_phones(["AE1", "IY0"])
    # Two adjacent nuclei with no consonant between become two syllables
    assert len(syls) == 2
    assert syls[0].nucleus == "AE"
    assert syls[1].nucleus == "IY"


def test_parse_phones_two_consonant_cluster() -> None:
    """Verify a two-consonant cluster splits with the first as coda."""
    analyzer = EnglishAnalyzer()
    # B AE1 K T IH0: the KT cluster between nuclei has K as coda, T as onset
    syls = analyzer._parse_phones(["B", "AE1", "K", "T", "IH0"])
    assert len(syls) == 2
    assert syls[0].coda == "K"
    assert syls[1].onset == "T"


def test_fallback_analyze_no_vowels() -> None:
    """Verify a vowel-less unknown word falls back to one syllable (269)."""
    analyzer = EnglishAnalyzer()
    syls = analyzer._fallback_analyze("nth")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_french_syllabify_empty_word() -> None:
    """Verify a word cleaned to an empty string gets a "?" placeholder (174)."""
    analyzer = FrenchAnalyzer()
    syls = analyzer._syllabify_word("'")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_french_rhyme_key_nasal_back() -> None:
    """Verify the nasal back vowel merges to 'on' (line 216)."""
    analyzer = FrenchAnalyzer()
    assert analyzer.rhyme_key("bon") == "on"


def test_french_rhyme_key_placeholder_nucleus() -> None:
    """Verify a placeholder-nucleus word returns an empty rhyme key (233)."""
    analyzer = FrenchAnalyzer()
    assert analyzer.rhyme_key("'") == ""


def test_french_count_syllables_in_word() -> None:
    """Verify the per-word syllable count helper (line 245)."""
    analyzer = FrenchAnalyzer()
    assert analyzer.count_syllables_in_word("bon") == 1


def test_french_syllabify_line_skips_empty_syls() -> None:
    """Verify line syllabification skips vowel-less empty words (line 276)."""
    analyzer = FrenchAnalyzer()
    # "bc" has no vowel -> empty list, skipped; "bon" contributes 1 syllable
    syls = analyzer.syllabify_line("bc bon")
    assert len(syls) == 1
    assert syls[0].nucleus == "on"


def test_french_syllabify_line_liaison() -> None:
    """Verify cross-word liaison moves the coda into the next onset (285-286)."""
    analyzer = FrenchAnalyzer()
    # chat (coda t) + ami (initial vowel) -> liaison gives ami onset "t"
    syls = analyzer.syllabify_line("chat ami")
    assert syls[0].coda == ""
    assert syls[1].onset == "t"


def test_french_analyze_line_variants() -> None:
    """Verify line variants return only the standard syllabification (310)."""
    analyzer = FrenchAnalyzer()
    variants = analyzer.analyze_line_variants("bon")
    assert len(variants) == 1
    assert len(variants[0]) == 1


def test_french_silent_u_after_qu() -> None:
    """Verify u after qu is silent, so que/qui/quand count as one syllable."""
    analyzer = FrenchAnalyzer()
    assert analyzer.count_syllables_in_word("quel") == 1
    assert analyzer.count_syllables_in_word("que") == 1
    assert analyzer.count_syllables_in_word("qui") == 1
    assert analyzer.count_syllables_in_word("quand") == 1
    assert analyzer.count_syllables_in_word("nuit") == 1
    assert analyzer.count_syllables_in_word("coup") == 1


def test_french_silent_u_after_gu_front_vowel() -> None:
    """Verify u after gu is silent before e/i/y but a vowel otherwise (gu)."""
    analyzer = FrenchAnalyzer()
    # guerre: the u after gu is silent and final e muet drops -> 1 syllable
    assert analyzer.count_syllables_in_word("guerre") == 1
    assert analyzer.count_syllables_in_word("guide") == 1
    # Final gu: u is pronounced (aigu = /e.gy/, 2 syllables)
    assert analyzer.count_syllables_in_word("aigu") == 2


def test_french_internal_apostrophe_words_not_mangled() -> None:
    """Verify words with an internal apostrophe are not stripped to 1 syllable."""
    analyzer = FrenchAnalyzer()
    assert analyzer.count_syllables_in_word("aujourd'hui") == 3
    assert analyzer.count_syllables_in_word("quelqu'un") == 2
    assert analyzer.count_syllables_in_word("presqu'ile") == 2


def test_french_elision_proclitics_counts() -> None:
    """Verify elided proclitic words count syllables as French reading does."""
    analyzer = FrenchAnalyzer()
    assert analyzer.count_syllables_in_word("l'amour") == 2
    assert analyzer.count_syllables_in_word("l'eau") == 1
    assert analyzer.count_syllables_in_word("d'avoir") == 2
    assert analyzer.count_syllables_in_word("j'ai") == 1
    assert analyzer.count_syllables_in_word("qu'il") == 1
