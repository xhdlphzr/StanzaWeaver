# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = set("aeiouàèéìòóùAEIOU")
_DIPHTHONGS = {"ia", "ie", "io", "iu", "ua", "ue", "uo", "ui", "ai", "ei", "oi", "au", "eu", "ou"}


class ItalianAnalyzer(SyllableAnalyzer):
    language = "it"

    def _count_syllables_in_word(self, word: str) -> int:
        word = word.lower().strip(".,;:!?\"'()[]{}")
        if not word:
            return 0
        i = 0
        n = len(word)
        count = 0
        while i < n:
            if word[i] in _VOWELS:
                count += 1
                if i + 1 < n and word[i:i + 2] in _DIPHTHONGS:
                    i += 1
            i += 1
        return count if count > 0 else 1

    def analyze_word(self, word: str) -> list[Syllable]:
        word = word.lower().strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        count = self._count_syllables_in_word(word)
        return [
            Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})
            for _ in range(count)
        ]

    def count_syllables(self, text: str) -> int:
        return sum(self._count_syllables_in_word(w) for w in text.split() if w.strip())
