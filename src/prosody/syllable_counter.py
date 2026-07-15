# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

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
