# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

from .base import SyllableAnalyzer
from .chinese import ChineseAnalyzer
from .english import EnglishAnalyzer

_ANALYZERS: dict[str, SyllableAnalyzer] = {
    "zh": ChineseAnalyzer(),
    "en": EnglishAnalyzer(),
}


def register_analyzer(language: str, analyzer: SyllableAnalyzer):
    _ANALYZERS[language] = analyzer


def get_analyzer(language: str) -> SyllableAnalyzer:
    if language in _ANALYZERS:
        return _ANALYZERS[language]
    raise ValueError(f"No syllable analyzer registered for language: {language}")


def count_syllables(text: str, language: str) -> int:
    return get_analyzer(language).count_syllables(text)


def analyze_line(line: str, language: str) -> list:
    analyzer = get_analyzer(language)
    if language == "zh":
        chars = analyzer.tokenize_line(line)
        syllables = []
        for ch in chars:
            analyzed = analyzer.analyze_word(ch)
            if analyzed:
                syllables.append(analyzed[0])
        return syllables
    else:
        words = analyzer.tokenize_line(line)
        syllables = []
        for w in words:
            analyzed = analyzer.analyze_word(w)
            syllables.extend(analyzed)
        return syllables
