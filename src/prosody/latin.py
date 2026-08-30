# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""拉丁语音节分析器。

- 支持长音符号（āēīōūȳ）与短音符号（ăĕĭŏŭ）标注。
- 音长判定：词典/符号标注优先；无标注时双元音（ae/oe/au/eu/ei/ui）为长音，
  元音后跟两个及以上辅音（含跨词）为长音，其余为短音。
- qu/gu/su 后接元音时 u 为辅音性（quō、lingua、suāvis），不构成音节。
"""

import unicodedata

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
    "AE",
    "OE",
    "AU",
    "EU",
    "EI",
}
# 拉丁语塞音（muta）：与流音(l/r)相邻构成 muta cum liquida，仅算一个辅音位。
# 注意：f 是擦音而非塞音，不计入；故 "fl"/"fr" 不算 muta cum liquida。
_STOPS: set[str] = set("bcdgkpqt")

# 仅用于判定词尾/词首是否为元音（去组合音标后）。
_VOWEL_BASE: set[str] = set("aeiouy")


def _strip_macron(text: str) -> str:
    """去除组合音标（macron/短音符号），仅保留 ASCII 小写字母。

    用于把 "āe" 等带长音符号的双元音归一为 "ae" 后再查表。

    Args:
        text: 可能含组合音标的字符串。

    Returns:
        去组合音标后的纯 ASCII 小写形式。
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


class LatinAnalyzer(SyllableAnalyzer):
    """拉丁语音节分析器：音节切分 + 音长判定（符号/双元音/辅音位置）。"""

    language = "la"

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词的音节与音长。

        音节 = (onset 辅音) + 元音核(可含双元音) + (coda 辅音)。
        - 辅音性 u（qu/gu/su 后接元音）整簇作为当前音节的 onset，不构成独立音节。
        - muta cum liquida（塞音 + 流音簇）附于当前音节（计入 onset），不向后拆分；
          其余后置辅音归当前音节 coda（除末辅音外；音长由 coda 有效辅音位决定）。
        - 音长：长音符号/双元音为长；coda 有效辅音位 ≥ 2 亦为长（x 计 2 位）。

        Args:
            word: 拉丁语单词（可含长短音符号）。

        Returns:
            音节列表（长度标在 attributes["length"]）。
        """
        word = word.strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        syllables: list[Syllable] = []
        onset = ""
        nucleus = ""
        coda = ""
        length_val = ""

        def _close() -> None:
            """关闭当前挂起音节并追加到音节列表，随后重置本地的 onset/nucleus/coda/length。"""
            syllables.append(
                Syllable(
                    onset=onset,
                    nucleus=nucleus,
                    coda=coda,
                    attributes={
                        "tone": "",
                        "stress": "",
                        "length": length_val or "short",
                    },
                )
            )

        i = 0
        n = len(word)
        trailing: list[str] = []
        while i < n:
            ch = word[i]
            lower = ch.lower()
            # 辅音性 u: qu / gu / su 后接元音时整簇附于 trailing，作为下一音节 onset。
            if lower == "q" or (
                lower in "gs"
                and i + 1 < n
                and word[i + 1].lower() == "u"
                and i + 2 < n
                and word[i + 2] in _VOWELS
            ):
                if nucleus:
                    coda = "".join(trailing)
                    _close()
                    onset = ""
                    nucleus = ""
                    coda = ""
                    length_val = ""
                trailing.append(lower)
                trailing.append("u")
                i += 2
                continue
            if ch in _VOWELS:
                if nucleus:
                    _close()
                    onset = ""
                    nucleus = ""
                    coda = ""
                    length_val = ""
                vowel_base = ch
                is_long = False
                if ch in _LONG_MARKERS:
                    vowel_base = _LONG_MARKERS[ch]
                    is_long = True
                elif ch in _SHORT_MARKERS:
                    vowel_base = _SHORT_MARKERS[ch]
                cand_norm = (
                    _strip_macron(lower + word[i + 1].lower()) if i + 1 < n else ""
                )
                if i + 1 < n and cand_norm in _DIPHTHONGS:
                    nucleus = cand_norm
                    is_long = True
                    i += 1
                else:
                    nucleus = vowel_base.lower()

                # 累积的前导辅音成为当前音节 onset
                onset = "".join(trailing)
                trailing = []

                # 收集后续辅音，遇元音或辅音性 u 停止
                j = i + 1
                cons: list[str] = []
                while (
                    j < n
                    and word[j] not in _VOWELS
                    and not (
                        word[j].lower() == "q"
                        or (
                            word[j].lower() in "gs"
                            and j + 1 < n
                            and word[j + 1].lower() == "u"
                            and j + 2 < n
                            and word[j + 2] in _VOWELS
                        )
                    )
                ):
                    if word[j] not in " .-":
                        cons.append(word[j].lower())
                    j += 1
                trailing = cons
                eff = 0
                for c in cons:
                    eff += 2 if c == "x" else 1
                if not is_long and eff >= 2:
                    is_long = True
                length_val = "long" if is_long else "short"
                i = j
            else:
                trailing.append(lower)
                i += 1

        if nucleus:
            coda = "".join(trailing)
            _close()

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
        """整行分析（含跨词音长与拉丁省音 elision）。

        跨词音长：前词末元音后接后词首 ≥2 辅音则为长音。
        省音：前词以元音（或 m）结尾、后词以元音（或 h）开头时，
        前词末音节被吞掉，音节总数减一。

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
            if not syls:
                continue
            elided = False
            if wi + 1 < m:
                last_char = w[-1].lower()
                if last_char in _VOWEL_BASE or last_char == "m":
                    nxt_word = words[wi + 1].lower()
                    nstart_char = next((c for c in nxt_word if c.isalpha()), "")
                    if nstart_char in _VOWEL_BASE or nxt_word.startswith("h"):
                        elided = True
            if elided:
                # 省音：前词末元音（或 m）被后词首元音/h 吞掉，减少一个音节。
                syls = syls[:-1]
            elif wi + 1 < m:
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

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """整行切分变体（拉丁语标准切分下 muta cum liquida 并入一节拍，故仅返回标准切分）。

        Args:
            line: 一行拉丁语诗。

        Returns:
            仅含标准切分的变体列表。
        """
        return [self.analyze_line(line)]
