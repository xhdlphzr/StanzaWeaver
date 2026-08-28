# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""拉丁语音节分析器。

- 支持长音符号（āēīōūȳ）与短音符号（ăĕĭŏŭ）标注。
- 音长判定：词典/符号标注优先；无标注时双元音（ae/oe/au/eu/ei/ui）为长音，
  元音后跟两个及以上辅音（含跨词）为长音，其余为短音。
- qu/gu/su 后接元音时 u 为辅音性（quō、lingua、suāvis），不构成音节。
"""

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_LONG_MARKERS: dict[str, str] = {
    "ā": "a",
    "ē": "e",
    "ī": "i",
    "ō": "o",
    "ū": "u",
    "ȳ": "y",
    "Ā": "a",
    "Ē": "e",
    "Ī": "i",
    "Ō": "o",
    "Ū": "u",
    "Ȳ": "y",
}
_SHORT_MARKERS: dict[str, str] = {
    "ă": "a",
    "ĕ": "e",
    "ĭ": "i",
    "ŏ": "o",
    "ŭ": "u",
    "y̆": "y",
    "Ă": "a",
    "Ĕ": "e",
    "Ĭ": "i",
    "Ŏ": "o",
    "Ŭ": "u",
}
_VOWELS: set[str] = set("aeiouyāēīōūȳăĕĭŏŭAEIOUY")
_DIPHTHONGS: set[str] = {
    "ae",
    "oe",
    "au",
    "eu",
    "ei",
    "ui",
    "AE",
    "OE",
    "AU",
    "EU",
    "EI",
    "UI",
}
# 拉丁语塞音（muta）：与流音(l/r)相邻构成 muta cum liquida，仅算一个辅音位
_STOPS: set[str] = set("bcdfgkpqt")


class LatinAnalyzer(SyllableAnalyzer):
    """拉丁语音节分析器：音节切分 + 音长判定（符号/双元音/辅音位置）。"""

    language = "la"

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词的音节与音长。

        Args:
            word: 拉丁语单词（可含长短音符号）。

        Returns:
            音节列表（长度标在 attributes["length"]）。
        """
        word = word.strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        syllables: list[Syllable] = []
        i = 0
        n = len(word)
        onset = ""
        nucleus = ""
        length_val = ""

        while i < n:
            ch = word[i]
            # 辅音性 u: qu / gu / su 后接元音时 u 不构成音节（quō, lingua, suāvis）
            if ch.lower() == "q" or (
                ch.lower() in "gs"
                and i + 1 < n
                and word[i + 1].lower() == "u"
                and i + 2 < n
                and word[i + 2] in _VOWELS
            ):
                onset += ch.lower()
                if i + 1 < n and word[i + 1].lower() == "u":
                    onset += "u"
                    i += 1
                i += 1
                continue
            if ch in _VOWELS:
                if nucleus:
                    syllables.append(
                        Syllable(
                            onset=onset,
                            nucleus=nucleus,
                            attributes={"tone": "", "stress": "", "length": length_val},
                        )
                    )
                    onset = ""
                    length_val = ""
                vowel_base = ch
                is_long = False
                if ch in _LONG_MARKERS:
                    vowel_base = _LONG_MARKERS[ch]
                    is_long = True
                elif ch in _SHORT_MARKERS:
                    vowel_base = _SHORT_MARKERS[ch]

                if i + 1 < n and ch.lower() + word[i + 1].lower() in _DIPHTHONGS:
                    nucleus = ch.lower() + word[i + 1].lower()
                    is_long = True
                    i += 1
                else:
                    nucleus = vowel_base.lower()

                j = i + 1
                consonants: list[str] = []
                while j < n and word[j] not in _VOWELS:
                    if word[j] not in " .-":
                        consonants.append(word[j].lower())
                    j += 1
                # x 计为两个辅音(ks)；muta cum liquida（塞音+流音）仅算一个辅音位
                eff = 0
                for c in consonants:
                    eff += 2 if c == "x" else 1
                if (
                    len(consonants) == 2
                    and consonants[0] in _STOPS
                    and consonants[1] in "lr"
                ):
                    eff = 1
                if not is_long and eff >= 2:
                    is_long = True
                length_val = "long" if is_long else "short"
            else:
                onset += ch.lower()
            i += 1

        if nucleus:
            syllables.append(
                Syllable(
                    onset=onset,
                    nucleus=nucleus or "?",
                    attributes={
                        "tone": "",
                        "stress": "",
                        "length": length_val or "short",
                    },
                )
            )
        elif onset:
            syllables.append(
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            )

        return (
            syllables
            if syllables
            else [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]
        )

    def analyze_line(self, text: str) -> list[Syllable]:
        """整行分析（含跨词音长：前词末元音后接后词首 ≥2 辅音则为长音）。

        Args:
            text: 一行拉丁语文本。

        Returns:
            音节列表。
        """
        import re

        words = [w for w in re.split(r"[^A-Za-zāēīōūȳăĕĭŏŭ'-]+", text) if w]
        result: list[Syllable] = []
        m = len(words)
        for wi, w in enumerate(words):
            syls = self.analyze_word(w)
            if wi + 1 < m and syls:
                lead = self._leading_consonant_count(words[wi + 1])
                if lead >= 2:
                    syls[-1].attributes["length"] = "long"
            result.extend(syls)
        return result

    @staticmethod
    def _leading_consonant_count(w: str) -> int:
        """统计词首辅音序列的「有效辅音位」数（含 x 计2、qu/gu/su 的 u 为辅音性、

        muta cum liquida 仅算1）。

        Args:
            w: 拉丁语单词。

        Returns:
            有效辅音位数；无前导辅音返回 0。
        """
        w = w.strip(".,;:!?\"'()[]{}").lower()
        n = len(w)
        i = 0
        cons: list[str] = []
        while i < n and w[i] not in _VOWELS:
            ch = w[i]
            if ch in "qgs" and i + 1 < n and w[i + 1] == "u":
                cons.append(ch + "u")
                i += 2
                continue
            cons.append(ch)
            i += 1
        eff = 0
        for c in cons:
            eff += 2 if c == "x" else 1
        if len(cons) == 2 and cons[0][0] in _STOPS and cons[1][0] in "lr":
            eff = 1
        return eff

    def count_syllables(self, text: str) -> int:
        """逐词统计音节总数。

        Args:
            text: 拉丁语文本。

        Returns:
            音节总数。
        """
        return sum(len(self.analyze_word(w)) for w in text.split() if w.strip())
