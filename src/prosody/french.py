# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = set("aeiouyàâäéèêëîïôöùûüÿ")
_FR_DIGRAPHS = {
    "ou",
    "au",
    "eau",
    "ai",
    "ei",
    "eu",
    "oi",
    "ui",
    "ay",
    "ey",
    "œu",
    "œ",
    "an",
    "en",
    "in",
    "on",
    "un",
    "am",
    "em",
    "im",
    "om",
    "um",
    "ain",
    "ein",
    "oin",
}
_SILENT_E_RE = re.compile(r"e(s|nt)?$", re.I)
_ELISION_WORDS = {
    "l'",
    "d'",
    "s'",
    "n'",
    "c'",
    "j'",
    "m'",
    "t'",
    "qu'",
    "jusqu'",
    "lorsqu'",
    "puisqu'",
    "quoiqu'",
}
_APOSTROPHE_RE = re.compile(r"^[a-zA-Zàâäéèêëîïôöùûüÿ]*['’]")


class FrenchAnalyzer(SyllableAnalyzer):
    language = "fr"

    def _syllabify_word(self, word: str) -> list[Syllable]:
        w = word.lower().strip(".,;:!?\"'()[]{}")
        if not w:
            return []
        if w in _ELISION_WORDS:
            w = _APOSTROPHE_RE.sub("", w)
            if not w:
                return [
                    Syllable(
                        nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                    )
                ]
        else:
            w = _APOSTROPHE_RE.sub("", w)
        w = _SILENT_E_RE.sub("", w)
        if not w:
            return [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]
        syls = []
        i = 0
        n = len(w)
        onset = ""
        while i < n:
            if w[i] in _VOWELS:
                nucleus = None
                for length in [3, 2]:
                    if i + length <= n and w[i : i + length] in _FR_DIGRAPHS:
                        nucleus = w[i : i + length]
                        i += length
                        break
                if nucleus is None:
                    nucleus = w[i]
                    i += 1
                coda = ""
                while i < n and w[i] not in _VOWELS:
                    coda += w[i]
                    i += 1
                syls.append(
                    Syllable(
                        onset=onset,
                        nucleus=nucleus,
                        coda=coda,
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                )
                onset = ""
            else:
                onset += w[i]
                i += 1
        if not syls:
            syls.append(
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            )
        return syls

    def rhyme_key(self, word: str) -> str:
        """法语韵脚 key：最后一个发音的元音（含鼻化、二合元音）+ 其后全部辅音。
        静音 e 不构成韵脚元音（parle → 'arl'，belle → 'ell'）。"""
        syls = self._syllabify_word(word)
        if not syls:
            return ""
        last = syls[-1]
        if last.nucleus == "?":
            return ""
        return last.nucleus + last.coda

    def _count_syllables_in_word(self, word: str) -> int:
        return len(self._syllabify_word(word))

    def analyze_word(self, word: str) -> list[Syllable]:
        return self._syllabify_word(word)

    def count_syllables(self, text: str) -> int:
        return sum(self._count_syllables_in_word(w) for w in text.split() if w.strip())
