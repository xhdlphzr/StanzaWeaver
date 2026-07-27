# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from ..models.syllable import Syllable


class SyllableAnalyzer(ABC):
    language: str = ""

    @abstractmethod
    def analyze_word(self, word: str) -> list[Syllable]: ...

    @abstractmethod
    def count_syllables(self, text: str) -> int: ...

    def tokenize_line(self, line: str) -> list[str]:
        return line.split()
