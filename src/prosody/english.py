# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""英语音节分析器（基于 CMUdict）。

- CMUdict 音素串 → 音节切分，采用英语常规划音规则分配跨音节辅音。
- 主重音(1)与次重音(2)均视为重读（诗歌格律中次重音同样承担重音位置）。
- 多音词保留全部发音（read/present/record 等按词性、意义有不同读音），
  校验时任一发音变体满足格律即通过。
- rhyme_tail 生成严格重音押韵 key：最后一个重读元音起到词尾的音素串
  （含重音层级），用于商籁体/双行体等的押韵校验。
"""

import re
import threading

import nltk  # type: ignore[import-untyped]

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_NUMBERS_RE = re.compile(r"\d+")

_VOWEL_PHONEMES = {
    "AA",
    "AE",
    "AH",
    "AO",
    "AW",
    "AX",
    "AXR",
    "AY",
    "EH",
    "ER",
    "EY",
    "IH",
    "IX",
    "IY",
    "OW",
    "OY",
    "UH",
    "UW",
    "UX",
}

# 主重音(1)与次重音(2)均为重读（诗歌格律中次重音同样承担重音位置）；
# 轻音(0)标记为非重音(light)，与模板中 _l 约束一致，确保抑扬格的弱位被强制为非重读
_STRESS_MAP: dict[str, str] = {"0": "light", "1": "heavy", "2": "heavy"}

_ARPABET_TO_PHONEMES: dict[str, list[list[str]]] = {}
_cmudict_loaded = False
_cmudict_lock = threading.Lock()


def _load_cmudict() -> None:
    """惰性加载 CMUdict 到内存（线程安全，仅加载一次）。

    保留每个词的全部发音变体。
    """
    global _cmudict_loaded
    if _cmudict_loaded:
        return
    with _cmudict_lock:
        if _cmudict_loaded:
            return
        try:
            nltk.data.find("corpora/cmudict.zip")
        except LookupError:
            nltk.download("cmudict", quiet=True)
        from nltk.corpus import cmudict  # type: ignore[import-untyped]

        for word, pronunciations in cmudict.dict().items():
            _ARPABET_TO_PHONEMES[str(word)] = pronunciations
        _cmudict_loaded = True


class EnglishAnalyzer(SyllableAnalyzer):
    """英语音节分析器：音节切分 + 重音标注 + 多音变体 + 押韵尾串。"""

    language = "en"

    def _get_pronunciations(self, word: str) -> list[list[str]]:
        """查询词的全部音素发音。

        Args:
            word: 英文单词。

        Returns:
            音素列表的列表（每个元素是一个发音）；未知词返回空列表。
        """
        _load_cmudict()
        return _ARPABET_TO_PHONEMES.get(word.lower(), [])

    def analyze_variants(self, word: str) -> list[list[Syllable]]:
        """返回该词全部发音的音节切分结果。

        Args:
            word: 英文单词。

        Returns:
            每种发音对应一个音节列表；未知词退回启发式切分。
        """
        prons = self._get_pronunciations(word)
        if not prons:
            return [self._fallback_analyze(word)]
        return [self._parse_phones(p) for p in prons]

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词（取第一个发音，即 CMUdict 中最常见读音）。

        Args:
            word: 英文单词。

        Returns:
            音节列表。
        """
        return self.analyze_variants(word)[0]

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """整行的候选音节切分：逐词取全部发音变体组合（上限 64 种）。

        Args:
            line: 一行诗（可为多词）。

        Returns:
            候选切分列表（至少含一个元素）。
        """
        words = [w for w in re.split(r"[^a-zA-Z0-9'-]+", line.lower()) if w]
        combos: list[list[Syllable]] = [[]]
        for w in words:
            variants = self.analyze_variants(w)
            new: list[list[Syllable]] = []
            for combo in combos:
                for v in variants:
                    new.append(combo + v)
                    if len(new) >= 64:
                        break
                if len(new) >= 64:
                    break
            combos = new[:64]
        return combos or [[]]

    def _parse_phones(self, phones: list[str]) -> list[Syllable]:
        """CMUdict 音素串 → 音节切分。

        跨音节辅音归属规则（英语常规划音）：
        - 两个元音之间的单个辅音：前一元音为主重音、后一元音非主重音时
          收前音节（hap-py, bet-ter, bi-ol-o-gy）；否则归后一音节（a-bout, re-spond）。
        - 两个及以上的辅音簇：首辅音收前音节，其余归后一音节（ex-tra, Mon-day）。

        Args:
            phones: CMUdict 音素列表（含重音数字，如 ["B", "AE1", "T"]）。

        Returns:
            音节列表。
        """
        vpos = [
            i for i, p in enumerate(phones) if _NUMBERS_RE.sub("", p) in _VOWEL_PHONEMES
        ]
        if not vpos:
            return []

        n = len(phones)
        onset_runs: list[list[str]] = []
        for k, vi in enumerate(vpos):
            start = 0 if k == 0 else vpos[k - 1] + 1
            onset_runs.append([phones[j] for j in range(start, vi)])
        final_coda = [phones[j] for j in range(vpos[-1] + 1, n)]

        codas: list[list[str]] = [[] for _ in vpos]
        for k in range(len(vpos) - 1):
            run = onset_runs[k + 1]
            if not run:
                continue
            prev_stress = _NUMBERS_RE.search(phones[vpos[k]])
            curr_stress = _NUMBERS_RE.search(phones[vpos[k + 1]])
            prev_primary = prev_stress is not None and prev_stress.group() == "1"
            curr_primary = curr_stress is not None and curr_stress.group() == "1"
            if len(run) == 1 and prev_primary and not curr_primary:
                codas[k] = run
                onset_runs[k + 1] = []
            elif len(run) >= 2:
                codas[k] = run[:1]
                onset_runs[k + 1] = run[1:]
        codas[-1] = final_coda

        syllables: list[Syllable] = []
        for k, vi in enumerate(vpos):
            sm = _NUMBERS_RE.search(phones[vi])
            stress = _STRESS_MAP.get(sm.group() if sm else "", "")
            syllables.append(
                Syllable(
                    onset="".join(_NUMBERS_RE.sub("", p) for p in onset_runs[k]),
                    nucleus=_NUMBERS_RE.sub("", phones[vi]),
                    coda="".join(_NUMBERS_RE.sub("", p) for p in codas[k]),
                    attributes={"tone": "", "stress": stress, "length": ""},
                )
            )
        return syllables

    def rhyme_tail(self, word: str) -> str | None:
        """最后一个重读元音（主/次重音）起到词尾的音素串（含重音标记）。

        Args:
            word: 英文单词。

        Returns:
            押韵尾串（如 "AY1 T"）；无重读音节时返回 None（不能作韵脚）。
        """
        prons = self._get_pronunciations(word)
        if not prons:
            return None
        for phones in prons:
            for i in range(len(phones) - 1, -1, -1):
                sm = _NUMBERS_RE.search(phones[i])
                if (
                    sm
                    and sm.group() in ("1", "2")
                    and _NUMBERS_RE.sub("", phones[i]) in _VOWEL_PHONEMES
                ):
                    return " ".join(phones[i:])
        return None

    def _fallback_analyze(self, word: str) -> list[Syllable]:
        """未知词启发式切分：按元音字母组数估音节数。

        Args:
            word: 不在 CMUdict 中的词。

        Returns:
            每个元音组一个占位音节（nucleus="?"，无重音）。
        """
        vowel_groups = re.findall(r"[aeiouy]+", word.lower())
        count = len(vowel_groups)
        if count == 0:
            count = 1
        return [
            Syllable(
                nucleus="?",
                attributes={"tone": "", "stress": "light", "length": ""},
            )
            for _ in range(count)
        ]

    def count_syllables(self, text: str) -> int:
        """逐词统计音节总数。

        Args:
            text: 英文文本。

        Returns:
            音节总数。
        """
        total = 0
        for word in text.split():
            total += len(self.analyze_word(word))
        return total
