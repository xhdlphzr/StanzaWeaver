# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = "aeiouàèéìòóù"
_DIPHTHONG_PATTERNS = ["ia", "ie", "io", "iu", "ua", "ue", "uo", "ui", "ai", "ei", "oi", "au", "eu"]


class ItalianAnalyzer(SyllableAnalyzer):
    language = "it"

    def analyze_word(self, word: str) -> list[Syllable]:
        word = word.lower().strip(".,;:!?\"'()[]{}")
        if not word:
            return []

        syllables = []
        i = 0
        n = len(word)
        onset_chars = []
        in_nucleus = False
        current_nucleus = ""

        while i < n:
            ch = word[i]
            if ch in _VOWELS:
                if in_nucleus and i > 0 and word[i - 1] in _VOWELS:
                    check = word[i - 1 : i + 1]
                    if check in _DIPHTHONG_PATTERNS and i > 1 and word[i - 2] not in _VOWELS:
                        current_nucleus += ch
                        i += 1
                        continue
                if in_nucleus:
                    syllables.append(
                        Syllable(
                            onset="".join(onset_chars),
                            nucleus=current_nucleus,
                            attributes={"tone": "", "stress": "", "length": ""},
                        )
                    )
                    onset_chars = []
                current_nucleus = ch
                in_nucleus = True
            else:
                if in_nucleus:
                    onset_chars.append(ch)
                else:
                    onset_chars.append(ch)
            i += 1

        if in_nucleus or onset_chars:
            syllables.append(
                Syllable(
                    onset="".join(onset_chars) if in_nucleus else "",
                    nucleus=current_nucleus if in_nucleus else "?",
                    attributes={"tone": "", "stress": "", "length": ""},
                )
            )

        return syllables if syllables else [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})]

    def count_syllables(self, text: str) -> int:
        return sum(len(self.analyze_word(w)) for w in text.split() if w.strip())
