# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = "aeiouyàâäéèêëîïôöùûüÿ"
_NASAL_PATTERNS = re.compile(r"[aeiou]in|[aeiou]im|[aeiou]en|[aeiou]em|[aeiou]an|[aeiou]am|[aeiou]on|[aeiou]om|[aeiou]un|[aeiou]um", re.I)
_SILENT_E_PATTERN = re.compile(r"e(s|nt)?$", re.I)


class FrenchAnalyzer(SyllableAnalyzer):
    language = "fr"

    def analyze_word(self, word: str) -> list[Syllable]:
        word = word.lower().strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        if word in {"l'", "d'", "s'", "n'", "c'", "j'", "m'", "t'", "qu'"}:
            return [Syllable(nucleus="e", attributes={"tone": "", "stress": "", "length": ""})]

        clean = word
        if not clean:
            return [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})]

        syllables = []
        i = 0
        n = len(clean)
        onset_chars = []
        current_nucleus = ""

        while i < n:
            ch = clean[i]
            if ch in _VOWELS:
                if current_nucleus:
                    if (_SILENT_E_PATTERN.search(clean) and i == n - 1
                            and ch == 'e' and onset_chars and onset_chars[-1] not in _VOWELS):
                        i += 1
                        continue
                    syllables.append(
                        Syllable(
                            onset="".join(onset_chars),
                            nucleus=current_nucleus or "?",
                            attributes={"tone": "", "stress": "", "length": ""},
                        )
                    )
                    onset_chars = []
                current_nucleus = ch
            else:
                if current_nucleus:
                    onset_chars.append(ch)
                else:
                    onset_chars.append(ch)
            i += 1

        if current_nucleus:
            syllables.append(
                Syllable(
                    onset="".join(onset_chars),
                    nucleus=current_nucleus,
                    attributes={"tone": "", "stress": "", "length": ""},
                )
            )
        elif onset_chars:
            syllables.append(
                Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})
            )

        return syllables if syllables else [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})]

    def count_syllables(self, text: str) -> int:
        words = text.split()
        total = 0
        for w in words:
            if not w.strip():
                continue
            total += len(self.analyze_word(w))
        return total
