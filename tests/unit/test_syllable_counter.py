# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the unified syllable counter and whole-line analysis entry point."""

import pytest

from src.models.syllable import Syllable
from src.prosody.base import SyllableAnalyzer
from src.prosody.syllable_counter import (
    analyze_line,
    count_syllables,
    get_analyzer,
    register_analyzer,
)


def test_count_syllables_zh() -> None:
    """Verify count_syllables for Chinese."""
    assert count_syllables("床前明月光", "zh") == 5


def test_analyze_line_zh_syllables() -> None:
    """Verify analyze_line returns syllables for Chinese."""
    syls = analyze_line("光", "zh")
    assert len(syls) == 1
    assert syls[0].nucleus == "ua"


def test_analyze_line_it_sinalefe() -> None:
    """Verify analyze_line merges adjacent vowels across words in Italian."""
    # "poeti e": adjacent vowels across words merge into one -> 3 syllables.
    assert count_syllables("poeti e", "it") == 3


def test_analyze_line_la_routes() -> None:
    """Verify analyze_line routes Latin lines to the Latin analyzer."""
    syls = analyze_line("amor", "la")
    assert all(isinstance(s, Syllable) for s in syls)
    assert len(syls) == 2


def test_get_analyzer_unknown_language() -> None:
    """Verify get_analyzer raises for an unknown language."""
    with pytest.raises(ValueError):
        get_analyzer("xx")


def test_register_analyzer_override() -> None:
    """Verify register_analyzer overrides an existing registration."""

    class Dummy(SyllableAnalyzer):
        """Stub analyzer used to test registration overrides."""

        language = "dummy"

        def analyze_word(self, word: str) -> list[Syllable]:
            """Return an empty syllable list.

            Args:
                word: Word to analyze.

            Returns:
                An empty list.

            """
            return []

        def count_syllables(self, text: str) -> int:
            """Count syllables."""
            return 0

    register_analyzer("dummy", Dummy())
    assert isinstance(get_analyzer("dummy"), Dummy)
    # Registering again overrides the previous entry (safe: no other test uses "dummy").
    register_analyzer("dummy", Dummy())
