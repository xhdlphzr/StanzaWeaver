# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_VOWELS = set("aeiouàèéìòóùAEIOUÀÈÉÌÒÓÙ")
_DIPHTHONGS = {"ia", "ie", "io", "iu", "ua", "ue", "uo", "ui", "ai", "ei", "oi", "au", "eu", "ou"}
_ACCENTED_VOWELS = set("àèéìòóù")
# 省音撇号（elision）：l'amor → amor；strip 前缀计数
_APOSTROPHE_RE = re.compile(r"^[a-zA-ZàèéìòóùÀÈÉÌÒÓÙ]*['’]")
_WORD_SPLIT_RE = re.compile(r"[^a-zA-ZàèéìòóùÀÈÉÌÒÓÙ0-9'’\-]+")


class ItalianAnalyzer(SyllableAnalyzer):
    language = "it"

    def _count_syllables_in_word(self, word: str) -> int:
        word = _APOSTROPHE_RE.sub("", word.lower().strip(".,;:!?\"'()[]{}"))
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

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """按词切分音节并标注重音（启发式）：
        - 词尾为重读元音（città, perché, virtù）或词尾为辅音（amor, piacer）→ 末音节重读；
        - 其余（词尾为普通元音）→ 倒数第二音节重读（意大利语最常见重音位置）。
        注：少数倒数第三音节重读的词（sdrucciole）无法由正字法判定，属已知局限。"""
        w = _APOSTROPHE_RE.sub("", word.lower())
        if not w:
            return []
        syls = []
        i = 0
        n = len(w)
        while i < n:
            if w[i] in _VOWELS:
                if i + 1 < n and w[i:i + 2] in _DIPHTHONGS:
                    nucleus = w[i:i + 2]
                    i += 2
                else:
                    nucleus = w[i]
                    i += 1
                coda = ""
                while i < n and w[i] not in _VOWELS:
                    coda += w[i]
                    i += 1
                syls.append(
                    Syllable(
                        nucleus=nucleus,
                        coda=coda,
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                )
            else:
                i += 1
        if not syls:
            return [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""})]

        final_char = w[-1]
        if final_char in _ACCENTED_VOWELS or final_char not in _VOWELS:
            stress_idx = len(syls) - 1
        else:
            stress_idx = len(syls) - 2 if len(syls) >= 2 else 0
        if 0 <= stress_idx < len(syls):
            syls[stress_idx].attributes["stress"] = "heavy"
        return syls

    def syllabify_line(self, text: str) -> list[Syllable]:
        """整行切分：逐词切分后应用 sinalefe（前词末元音与后词首元音并读为一个音节）。"""
        words = [w for w in _WORD_SPLIT_RE.split(text.lower()) if w]
        all_syls: list[Syllable] = []
        for wi, w in enumerate(words):
            syls = self._syllabify_word(w)
            if not syls:
                continue
            if wi > 0:
                prev_clean = _APOSTROPHE_RE.sub("", words[wi - 1])
                curr_clean = _APOSTROPHE_RE.sub("", w)
                if (
                    prev_clean
                    and curr_clean
                    and prev_clean[-1] in _VOWELS
                    and curr_clean[0] in _VOWELS
                    and all_syls
                    and all_syls[-1].coda == ""
                ):
                    # sinalefe: 前词末音节并入后词首音节，重音随之合并
                    prev_stress = all_syls[-1].attributes.get("stress") == "heavy"
                    all_syls.pop()
                    if prev_stress and syls:
                        syls[0].attributes["stress"] = "heavy"
            all_syls.extend(syls)
        return all_syls

    def analyze_word(self, word: str) -> list[Syllable]:
        return self._syllabify_word(word)

    def count_syllables(self, text: str) -> int:
        return len(self.syllabify_line(text))
