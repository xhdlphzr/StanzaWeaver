# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = set("aeiouyàâäéèêëîïôöùûüÿAEIOUY")
_FR_DIGRAPHS = {"ou", "au", "eau", "ai", "ei", "eu", "oi", "œu", "œ", "an", "en", "in", "on", "un", "am", "em", "im", "om", "um", "ain", "ein", "oin"}
_SILENT_E_RE = re.compile(r"e(s|nt)?$", re.I)
_ELISION_WORDS = {"l'", "d'", "s'", "n'", "c'", "j'", "m'", "t'", "qu'", "jusqu'", "lorsqu'", "puisqu'", "quoiqu'"}


class FrenchAnalyzer(SyllableAnalyzer):
    language = "fr"

    def _count_syllables_in_word(self, word: str) -> int:
        w = word.lower().strip(".,;:!?\"'()[]{}")
        if not w:
            return 0
        if w in _ELISION_WORDS or w.rstrip("'") in _ELISION_WORDS:
            return 1
        if _SILENT_E_RE.search(w):
            w = _SILENT_E_RE.sub("", w)
        if not w:
            return 1
        i = 0
        n = len(w)
        count = 0
        while i < n:
            if w[i] in _VOWELS:
                found = False
                for length in [3, 2]:
                    if i + length <= n and w[i:i + length] in _FR_DIGRAPHS:
                        count += 1
                        i += length
                        found = True
                        break
                if not found:
                    count += 1
                    i += 1
            else:
                i += 1
        return count if count > 0 else 1

    def analyze_word(self, word: str) -> list[Syllable]:
        word_lower = word.lower().strip(".,;:!?\"'()[]{}")
        if not word_lower:
            return []
        count = self._count_syllables_in_word(word_lower)
        return [
            Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})
            for _ in range(count)
        ]

    def count_syllables(self, text: str) -> int:
        return sum(self._count_syllables_in_word(w) for w in text.split() if w.strip())
