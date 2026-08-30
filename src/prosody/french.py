# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""法语音节分析器。

- 按正字法切分音节：二合/三合元音（ou/eau/ain 等）、鼻化元音、静音 e。
- 词尾静音 e 规则：仅当它为“弱”尾音节（与前一元音间仅隔 0~1 个辅音，
  或位于元音后形成元音重复）时才省略；否则计入（如 entre/table/porte）。
- 跨词省音（élision）与联诵（liaison）在整行切分中合并，避免重复计数。
- 韵脚 key 为词末发音元音核（鼻化归并），并丢弃词尾静音辅音。
"""

import re

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_VOWELS: set[str] = set("aeiouyàâäéèêëîïôöùûüæœÿ")
# 带分音符的元音不参与二合元音合并（如 naïf 的 ï）。
_TREMA: set[str] = {"ï", "ÿ", "ü"}

_FR_DIGRAPHS: set[str] = {
    # 三合元音 / 三字母核
    "eau",
    "yeu",
    "yen",
    "oui",
    "eui",
    "ien",
    "oin",
    "ain",
    "ein",
    # 二合元音 / 鼻化元音
    "ou",
    "au",
    "an",
    "en",
    "on",
    "in",
    "un",
    "ai",
    "ei",
    "eu",
    "oi",
    "ui",
    "ia",
    "ie",
    "io",
    "iu",
    "ua",
    "ue",
    "uo",
    # 原实现保留项
    "ay",
    "ey",
    "œu",
    "œ",
    "am",
    "em",
    "im",
    "om",
    "um",
}

# 词尾静音辅音（法语韵脚中忽略，如 s/t/x/p）。
_MUTE_FINALS: set[str] = set("stxp")

# 鼻化元音归并：前部鼻化 -> "an"，后部鼻化 -> "on"。
_NASAL_FRONT: set[str] = {
    "an",
    "en",
    "in",
    "un",
    "ain",
    "ein",
    "ien",
    "oin",
    "am",
    "em",
    "im",
    "um",
}
_NASAL_BACK: set[str] = {"on", "om"}

_APOSTROPHE_RE = re.compile(r"^[a-zA-Zàâäéèêëîïôöùûüÿæœ]*['’]")
_PUNCT_RE = re.compile(r"[^a-zàâäéèêëîïôöùûüæœÿ']")


def _is_vowel(ch: str) -> bool:
    """判断字符是否为法语元音（含重音与 œ/æ/y）。

    Args:
        ch: 单个字符。

    Returns:
        是元音返回 True。
    """
    return ch in _VOWELS


class FrenchAnalyzer(SyllableAnalyzer):
    """法语音节分析器：真实音节结构（韵腹/韵尾）+ 韵脚 key。"""

    language = "fr"

    def _clean_word(self, word: str) -> str:
        """去标点、去省音前缀并转小写。

        Args:
            word: 法语单词（可含 l'、d' 等省音前缀与标点）。

        Returns:
            清洗后的小写词；空串表示无实际内容。
        """
        w = word.lower().strip()
        w = _APOSTROPHE_RE.sub("", w)
        w = _PUNCT_RE.sub("", w)
        return w

    def _build_syllables(
        self, w: str, nuclei: list[tuple[int, int, str]]
    ) -> list[Syllable]:
        """根据元音核位置组装音节（辅音在核间归 onset，核后归 coda）。

        Args:
            w: 清洗后的词。
            nuclei: 由 (起始, 结束, 核文本) 组成的元音核列表。

        Returns:
            音节列表。
        """
        attrs: dict[str, str] = {"tone": "", "stress": "", "length": ""}
        syls: list[Syllable] = []
        prev_end = 0
        for idx, (start, end, nuc) in enumerate(nuclei):
            next_start = nuclei[idx + 1][0] if idx + 1 < len(nuclei) else len(w)
            onset = w[prev_end:start]
            coda = w[end:next_start]
            syls.append(
                Syllable(onset=onset, nucleus=nuc, coda=coda, attributes=dict(attrs))
            )
            prev_end = end
        return syls

    def _apply_final_e(
        self, syls: list[Syllable], w: str, nuclei: list[tuple[int, int, str]]
    ) -> list[Syllable]:
        """按规则省略词尾静音 e（若其为弱尾音节）。

        省略条件：末元音核恰为单字母 "e"，且 e 之后（词尾）仅含静音辅音；
        同时 e 与前一元音核之间仅隔 0~1 个辅音（即 e 非真实尾音节所必需）。
        唯一元音或与前一元音隔 2+ 辅音时保留。

        Args:
            syls: 初步切分出的音节。
            w: 清洗后的词。
            nuclei: 元音核列表。

        Returns:
            处理后的音节列表。
        """
        if not syls:
            return syls
        last = syls[-1]
        if last.nucleus != "e":
            return syls
        after = w[nuclei[-1][1] :]
        if after and not all(c in _MUTE_FINALS for c in after):
            return syls
        if len(syls) == 1:
            return syls
        if len(last.onset) >= 2:
            return syls
        return syls[:-1]

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """按词切分音节（处理二/三合元音与词尾静音 e）。

        Args:
            word: 法语单词（可含省音前缀与标点）。

        Returns:
            音节列表（nucleus 为真实元音核，coda 为尾辅音）。
        """
        w = self._clean_word(word)
        if not w:
            return [
                Syllable(
                    nucleus="?",
                    attributes={"tone": "", "stress": "", "length": ""},
                )
            ]

        nuclei: list[tuple[int, int, str]] = []
        i = 0
        n = len(w)
        while i < n:
            if _is_vowel(w[i]):
                matched: str | None = None
                for length in (3, 2):
                    if i + length <= n and w[i : i + length] in _FR_DIGRAPHS:
                        matched = w[i : i + length]
                        i += length
                        break
                if matched is None:
                    matched = w[i]
                    i += 1
                nuclei.append((i - len(matched), i, matched))
            else:
                i += 1

        syls = self._build_syllables(w, nuclei)
        return self._apply_final_e(syls, w, nuclei)

    def _normalize_nucleus(self, nuc: str) -> str:
        """将元音核归并到押韵等价类（鼻化合并）。

        Args:
            nuc: 原始元音核（可能为二/三合元音或鼻化元音）。

        Returns:
            归并后的韵脚核（前部鼻化 -> "an"，后部鼻化 -> "on"）。
        """
        if nuc in _NASAL_FRONT:
            return "an"
        if nuc in _NASAL_BACK:
            return "on"
        return nuc

    def rhyme_key(self, word: str) -> str:
        """法语韵脚 key：词末发音元音核（鼻化归并），词尾静音辅音已丢弃。

        Args:
            word: 行末词。

        Returns:
            韵脚串（如 parle -> "e"，an/en -> "an"）；无法切分时返回空串。
        """
        syls = self._syllabify_word(word)
        if not syls:
            return ""
        last = syls[-1]
        if last.nucleus == "?":
            return ""
        return self._normalize_nucleus(last.nucleus)

    def _count_syllables_in_word(self, word: str) -> int:
        """单词语节数（含二/三合元音合并与词尾静音 e 规则）。

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

    def syllabify_line(self, text: str) -> list[Syllable]:
        """整行切分：逐词切分并应用跨词省音与联诵。

        前词末音节以元音结尾、后词首音节以元音开头时，二者省音合并为
        一个音节；前词以辅音结尾、后词以元音开头时，该辅音作为联诵
        onset 并入后词首音节。两者均避免重复计数。

        Args:
            text: 一行法语诗。

        Returns:
            整行音节列表。
        """
        words = text.split()
        all_syls: list[Syllable] = []
        for w in words:
            syls = self._syllabify_word(w)
            if not syls:
                continue
            if all_syls and syls:
                prev = all_syls[-1]
                curr = syls[0]
                if prev.coda == "" and curr.onset == "":
                    # 省音：前词末元音与后词首元音合并
                    all_syls.pop()
                elif prev.coda != "" and curr.onset == "":
                    # 联诵：前词尾辅音成为后词首音节 onset
                    curr.onset = prev.coda
                    prev.coda = ""
            all_syls.extend(syls)
        return all_syls

    def count_syllables(self, text: str) -> int:
        """统计文本音节总数（含跨词省音/联诵合并）。

        Args:
            text: 法语文本（可为多词或整行）。

        Returns:
            音节总数。
        """
        return len(self.syllabify_line(text))

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """整行切分变体（法语标准音节划分下仅返回一种切分）。

        Args:
            line: 一行法语诗。

        Returns:
            仅含标准切分的变体列表。
        """
        return [self.syllabify_line(line)]
