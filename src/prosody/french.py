# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""法语音节分析器。

- 按正字法切分音节：二合/三合元音（ou/eau/ain 等）、鼻化元音、静音 e。
- 韵脚 key：最后一个发音元音 + 其后全部辅音（静音 e 不参与），
  供回旋诗/三韵叠句诗/叙事歌押韵校验。
"""

import re

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_VOWELS: set[str] = set("aeiouyàâäéèêëîïôöùûüÿ")
_FR_DIGRAPHS: set[str] = {
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
_SILENT_E_RE = re.compile(r"e(s|nt)?$", re.IGNORECASE)
_APOSTROPHE_RE = re.compile(r"^[a-zA-Zàâäéèêëîïôöùûüÿ]*['’]")


class FrenchAnalyzer(SyllableAnalyzer):
    """法语音节分析器：真实音节结构（韵腹/韵尾）+ 韵脚 key。"""

    language = "fr"

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """按词切分音节（去掉省音前缀与词尾静音 e）。

        Args:
            word: 法语单词（可含 l'、d' 等省音前缀）。

        Returns:
            音节列表（nucleus 为真实元音串，coda 为尾辅音）。
        """
        w = word.lower().strip(".,;:!?\"'()[]{}")
        if not w:
            return []
        w = _APOSTROPHE_RE.sub("", w)
        w = _SILENT_E_RE.sub("", w)
        if not w:
            return [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]
        syls: list[Syllable] = []
        i = 0
        n = len(w)
        onset = ""
        while i < n:
            if w[i] in _VOWELS:
                nucleus: str | None = None
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
        """法语韵脚 key：最后一个发音元音 + 其后全部辅音。

        Args:
            word: 行末词。

        Returns:
            韵脚串（parle → "arl"，belle → "ell"）；无法切分时返回空串。
        """
        syls = self._syllabify_word(word)
        if not syls:
            return ""
        last = syls[-1]
        if last.nucleus == "?":
            return ""
        return last.nucleus + last.coda

    def _count_syllables_in_word(self, word: str) -> int:
        """单词语节数。

        Args:
            word: 法语单词。

        Returns:
            音节数。
        """
        return len(self._syllabify_word(word))

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词的音节。

        Args:
            word: 法语单词。

        Returns:
            音节列表。
        """
        return self._syllabify_word(word)

    def count_syllables(self, text: str) -> int:
        """逐词统计音节总数。

        Args:
            text: 法语文本。

        Returns:
            音节总数。
        """
        return sum(self._count_syllables_in_word(w) for w in text.split() if w.strip())
