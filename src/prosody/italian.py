# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""意大利语音节分析器。

- 按正字法切分音节（二合元音并读），并按启发式标注词重音：
  词尾重读元音（città, perché, virtù）或辅音收尾（amor）→ 末音节重读；
  其余 → 倒数第二音节重读（意大利语最常见重音位置）。
  注：少数倒数第三音节重读的词（sdrucciole）无法由正字法判定，属已知局限。
- syllabify_line 处理行级 sinalefe（前词末元音与后词首元音并读为一个音节）
  与省音撇号（l'amor → amor），用于十一音节句计数。
"""

import re

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_VOWELS: set[str] = set("aeiouàèéìòóùAEIOUÀÈÉÌÒÓÙ")
_DIPHTHONGS: set[str] = {
    "ia",
    "ie",
    "io",
    "iu",
    "ua",
    "ue",
    "uo",
    "ui",
    "ai",
    "ei",
    "oi",
    "au",
    "eu",
    "ou",
}
_ACCENTED_VOWELS: set[str] = set("àèéìòóù")
_APOSTROPHE_RE = re.compile(r"^[a-zA-ZàèéìòóùÀÈÉÌÒÓÙ]*['’]")
_WORD_SPLIT_RE = re.compile(r"[^a-zA-ZàèéìòóùÀÈÉÌÒÓÙ0-9'’\-]+")


class ItalianAnalyzer(SyllableAnalyzer):
    """意大利语音节分析器：音节切分 + 重音启发式 + 行级 sinalefe。"""

    language = "it"

    def count_syllables_in_word(self, word: str) -> int:
        """单词语节数（含二合元音合并，重读元音视为元音分裂）。

        当候选二合元音 i/u 中任一字符带重音符号（à è é ì ò ó ù）时，
        不合并而计为两个音节（hiatus）。

        Args:
            word: 意大利语单词。

        Returns:
            音节数（至少 1）。
        """
        word = _APOSTROPHE_RE.sub("", word.lower().strip(".,;:!?\"'()[]{}"))
        if not word:
            return 0
        i = 0
        n = len(word)
        count = 0
        while i < n:
            if word[i] in _VOWELS:
                count += 1
                if (
                    i + 1 < n
                    and word[i : i + 2] in _DIPHTHONGS
                    and word[i] not in _ACCENTED_VOWELS
                    and word[i + 1] not in _ACCENTED_VOWELS
                ):
                    i += 1
            i += 1
        return count if count > 0 else 1

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """按词切分音节并标注重音（启发式）。

        重读元音（如 ì）所在的 i/u 与其后元音不构成二合元音，而是作为
        元音分裂计为两个音节。重音位置由 :meth:`_mark_word_stress` 判定。

        Args:
            word: 意大利语单词。

        Returns:
            音节列表（重音标在 attributes["stress"]，重读为 "heavy"）。
        """
        w = _APOSTROPHE_RE.sub("", word.lower())
        if not w:
            return []
        syls: list[Syllable] = []
        i = 0
        n = len(w)
        onset = ""
        while i < n:
            if w[i] in _VOWELS:
                if (
                    i + 1 < n
                    and w[i : i + 2] in _DIPHTHONGS
                    and w[i] not in _ACCENTED_VOWELS
                    and w[i + 1] not in _ACCENTED_VOWELS
                ):
                    nucleus = w[i : i + 2]
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
                        onset=onset,
                        nucleus=nucleus,
                        coda=coda,
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                )
                onset = ""
            elif w[i] == "q" and i + 1 < n and w[i + 1] == "u":
                onset += "qu"
                i += 2
            else:
                onset += w[i]
                i += 1
        if not syls:
            return [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]

        self._mark_word_stress(w, syls)
        return syls

    def _mark_word_stress(self, word: str, syls: list[Syllable]) -> None:
        """按启发式标注重音（写入各音节的 attributes["stress"]）。

        规则：
        - 含显式重音符号（à è é ì ò ó ù）的音节重读；
        - 以辅音结尾 -> 末音节重读（tronca）；
        - 以两个辅音结尾 -> 倒数第二音节重读；
        - 以元音结尾的多音节词 -> 倒数第二音节重读（piana）；
        - 单元音且无重音符号的词（如 la、mi）视为非重读小品词。

        Args:
            word: 已小写、去省音撇的纯字母词。
            syls: 已切分好的音节列表（就地修改）。
        """
        n = len(syls)
        accent_idx = -1
        for idx, s in enumerate(syls):
            if any(ch in _ACCENTED_VOWELS for ch in s.nucleus):
                accent_idx = idx
                break

        if accent_idx >= 0:
            stress_idx = accent_idx
        elif word[-1] not in _VOWELS:
            if len(word) >= 2 and word[-2] not in _VOWELS:
                stress_idx = n - 2
            else:
                stress_idx = n - 1
        elif n == 1:
            stress_idx = -1
        else:
            stress_idx = n - 2

        if 0 <= stress_idx < n:
            syls[stress_idx].attributes["stress"] = "heavy"

    def syllabify_line(self, text: str) -> list[Syllable]:
        """整行切分：逐词切分后应用 sinalefe 合并跨词元音。

        当词界处两元音相遇，但其中任一元音为重读（hiatus，如 virtù eterna）
        时，不执行 sinalefe，保留为两个独立音节。

        Args:
            text: 一行意大利语诗。

        Returns:
            整行音节列表（已处理省音与可能的 sinalefe 合并）。
        """
        words = [w for w in _WORD_SPLIT_RE.split(text.lower()) if w]
        all_syls: list[Syllable] = []
        for wi, w in enumerate(words):
            syls = self._syllabify_word(w)
            if not syls:
                continue
            if wi > 0:
                prev_clean = _APOSTROPHE_RE.sub("", words[wi - 1])
                curr_clean = _APOSTROPHE_RE.sub("", w)
                prev_syl = all_syls[-1] if all_syls else None
                can_sinalefe = (
                    prev_clean
                    and curr_clean
                    and prev_clean[-1] in _VOWELS
                    and curr_clean[0] in _VOWELS
                    and prev_syl is not None
                    and prev_syl.coda == ""
                )
                if can_sinalefe:
                    assert prev_syl is not None
                    prev_heavy = prev_syl.attributes.get("stress") == "heavy"
                    next_heavy = syls[0].attributes.get("stress") == "heavy"
                    if prev_heavy or next_heavy:
                        # 元音分裂（hiatus）：不合并，保留两个音节
                        pass
                    else:
                        all_syls.pop()
            all_syls.extend(syls)
        return all_syls

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词的音节与重音。

        Args:
            word: 意大利语单词。

        Returns:
            音节列表。
        """
        return self._syllabify_word(word)

    def count_syllables(self, text: str) -> int:
        """统计文本音节数（含 sinalefe 合并）。

        Args:
            text: 意大利语文本。

        Returns:
            音节总数。
        """
        return len(self.syllabify_line(text))

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """整行切分变体（意大利语标准诵读下 sinalefe 为强制，故仅返回标准切分）。

        Args:
            line: 一行意大利语诗。

        Returns:
            仅含标准切分（已应用 sinalefe）的变体列表。
        """
        return [self.syllabify_line(line)]
