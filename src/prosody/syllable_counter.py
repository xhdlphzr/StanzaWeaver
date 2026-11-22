# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unified multi-language syllable counting and whole-line analysis entry point.

Routes by language to the matching analyzer, always using
``analyze_line_variants`` as the single line-level convention: Chinese whole
lines go to pypinyin (context-aware polyphonic disambiguation), Italian lines
apply sinalefe merging, French lines apply cross-word liaison, Latin lines apply
elision and cross-word vowel length, and other languages are split word by word.
"""

from ..models.syllable import Syllable
from .base import SyllableAnalyzer
from .chinese import ChineseAnalyzer
from .english import EnglishAnalyzer
from .french import FrenchAnalyzer
from .italian import ItalianAnalyzer
from .latin import LatinAnalyzer

_ANALYZERS: dict[str, SyllableAnalyzer] = {
    "zh": ChineseAnalyzer(),
    "en": EnglishAnalyzer(),
    "it": ItalianAnalyzer(),
    "fr": FrenchAnalyzer(),
    "la": LatinAnalyzer(),
}


def register_analyzer(language: str, analyzer: SyllableAnalyzer) -> None:
    """Register (or override) the analyzer for a language.

    Args:
        language: Language code (zh/en/it/fr/la).
        analyzer: Analyzer instance.

    """
    _ANALYZERS[language] = analyzer


def get_analyzer(language: str) -> SyllableAnalyzer:
    """Get the analyzer for a language.

    Args:
        language: Language code.

    Returns:
        The matching analyzer instance.

    Raises:
        ValueError: If the language is not registered.

    """
    if language in _ANALYZERS:
        return _ANALYZERS[language]
    raise ValueError(f"No syllable analyzer registered for language: {language}")


def count_syllables(text: str, language: str) -> int:
    """Count the syllables in a text (same convention as whole-line analysis).

    Args:
        text: Arbitrary text.
        language: Language code.

    Returns:
        Total syllable count.

    """
    return len(analyze_line(text, language))


def analyze_line(line: str, language: str) -> list[Syllable]:
    """Analyze the syllables of a line (first non-empty variant).

    Delegates to the analyzer's ``analyze_line_variants`` and returns its first
    non-empty variant. Line-level features (Chinese polyphonic disambiguation,
    Italian sinalefe, French liaison, Latin elision, etc.) are provided
    uniformly by each analyzer's ``analyze_line_variants``.

    Args:
        line: One line of verse.
        language: Language code.

    Returns:
        Syllable list for the whole line; empty if there are no valid
        syllables.

    """
    for variant in get_analyzer(language).analyze_line_variants(line):
        if variant:
            return variant
    return []
