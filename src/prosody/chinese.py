# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""中文音节分析器（基于 pypinyin）。

- 韵母拆解表 FINAL_TO_PARTS：将拼音韵母拆为韵腹 + 韵尾。
- 整行分析时由调用方拼接全行后一次性交给 pypinyin，
  借助其词库按上下文消歧多音字（弹琴→tán、银行→háng）。
- 声调映射：1/2 声 → 平，3/4 声 → 仄，轻声 → 空。
"""

import warnings

# pypinyin<=0.55.0 在 Python 3.14 下触发 codecs.open() 弃用警告（第三方库未适配），
# 于 import 前屏蔽该特定警告
warnings.filterwarnings(
    "ignore",
    message=r"codecs\.open\(\) is deprecated.*",
    category=DeprecationWarning,
)

from pypinyin import Style, pinyin

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

FINAL_TO_PARTS: dict[str, tuple[str, str]] = {
    "a": ("a", ""),
    "o": ("o", ""),
    "e": ("e", ""),
    "i": ("i", ""),
    "u": ("u", ""),
    "v": ("v", ""),
    "ü": ("ü", ""),
    "er": ("er", ""),
    "ai": ("ai", ""),
    "ei": ("ei", ""),
    "ao": ("ao", ""),
    "ou": ("ou", ""),
    "iu": ("iu", ""),
    "ui": ("ui", ""),
    "an": ("a", "n"),
    "en": ("e", "n"),
    "in": ("i", "n"),
    "un": ("u", "n"),
    "vn": ("v", "n"),
    "ün": ("ü", "n"),
    "ang": ("a", "ng"),
    "eng": ("e", "ng"),
    "ing": ("i", "ng"),
    "ong": ("o", "ng"),
    "ia": ("ia", ""),
    "ie": ("ie", ""),
    "ua": ("ua", ""),
    "uo": ("uo", ""),
    "ve": ("ve", ""),
    "üe": ("üe", ""),
    "iao": ("iao", ""),
    "uai": ("uai", ""),
    "ian": ("ia", "n"),
    "uan": ("ua", "n"),
    "van": ("va", "n"),
    "üan": ("üa", "n"),
    "iang": ("ia", "ng"),
    "uang": ("ua", "ng"),
    "iong": ("io", "ng"),
    "ueng": ("ue", "ng"),
}

CHINESE_INITIALS = frozenset(
    {
        "b",
        "p",
        "m",
        "f",
        "d",
        "t",
        "n",
        "l",
        "g",
        "k",
        "h",
        "j",
        "q",
        "x",
        "zh",
        "ch",
        "sh",
        "r",
        "z",
        "c",
        "s",
        "y",
        "w",
    }
)

_PING_TONES = {"1", "2"}
_ZE_TONES = {"3", "4"}


def _split_final(final_str: str) -> tuple[str, str]:
    """将带声调的韵母串拆为 (韵腹, 韵尾)。

    Args:
        final_str: 如 "iao3"、"ang"、"üe4"。

    Returns:
        (韵腹, 韵尾)；无法识别时原样返回 (final_str, "")。
    """
    if not final_str:
        return "", ""
    tone_char = final_str[-1]
    if tone_char.isdigit():
        base = final_str[:-1]
    else:
        base = final_str
        tone_char = ""
    base_lower = base.lower()
    nucleus, coda = FINAL_TO_PARTS.get(base_lower, (base, ""))
    return nucleus, coda


def _tone_to_pingze(tone_str: str) -> str:
    """声调 → 平仄标签。

    一声、二声与轻声（含无调号）均归为平声；三声、四声归为仄声。

    Args:
        tone_str: 带声调数字的韵母串（如 "iao3"），无声调号（轻声/无调）
            或空串也按平声处理。

    Returns:
        "平" 或 "仄"。
    """
    if not tone_str:
        return "平"
    if tone_str[-1].isdigit():
        t = tone_str[-1]
    else:
        # 无声调号视为轻声 → 平声
        return "平"
    if t in _PING_TONES:
        return "平"
    if t in _ZE_TONES:
        return "仄"
    # 5 声（轻声）等非常规数字亦归平声
    return "平"


class ChineseAnalyzer(SyllableAnalyzer):
    """中文音节分析器：逐字输出声母/韵腹/韵尾 + 平仄。

    analyze_word 接受任意长度文本（含整行），pypinyin 会按短语上下文
    自动选择多音字的正确读音。
    """

    language = "zh"

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析中文文本（可多字）的音节，返回首选（第一）读音。

        为向后兼容保留单读音接口：返回 :meth:`analyze_word_variants` 的首个变体。

        Args:
            word: 中文文本，如 "弹琴" 或整行诗。

        Returns:
            每字一个 Syllable（平仄标在 attributes["tone"]）。
        """
        variants = self.analyze_word_variants(word)
        if not variants:
            return []
        return variants[0]

    def analyze_word_variants(self, word: str) -> list[list[Syllable]]:
        """返回某词的全部多音字读音组合（笛卡尔积）。

        对每个字调用 pypinyin 的 heteronym 模式，得到该字的候选
        (声母, 韵母) 列表，再对所有字做笛卡尔积，得到整词的全部读音。

        结果上限 64 种组合；超出时按生成顺序保留前 64 种（确定性截断）。

        Args:
            word: 中文文本，如 "中" 或 "弹琴"。

        Returns:
            读音列表；每个元素是一整词的 Syllable 序列（一种读法）。
        """
        if not word:
            return []

        initials_list = pinyin(word, style=Style.INITIALS, strict=False, heteronym=True)
        finals_list = pinyin(
            word, style=Style.FINALS_TONE3, strict=False, heteronym=True
        )

        # 逐字候选 Syllable 列表
        candidates: list[list[Syllable]] = []
        for initials, finals in zip(initials_list, finals_list):
            char_syls: list[Syllable] = []
            for onset_r in initials:
                for final_r in finals:
                    onset = str(onset_r) if onset_r else ""
                    final_raw = str(final_r) if final_r else ""
                    nucleus, coda = _split_final(final_raw)
                    tone_label = _tone_to_pingze(final_raw)
                    char_syls.append(
                        Syllable(
                            onset=onset,
                            nucleus=nucleus,
                            coda=coda,
                            attributes={
                                "tone": tone_label,
                                "stress": "",
                                "length": "",
                            },
                        )
                    )
            # 去重（按内容），保持顺序
            seen: set[tuple[str, str, str, str]] = set()
            deduped: list[Syllable] = []
            for syl in char_syls:
                key = (
                    syl.onset,
                    syl.nucleus,
                    syl.coda,
                    syl.attributes.get("tone", ""),
                )
                if key not in seen:
                    seen.add(key)
                    deduped.append(syl)
            candidates.append(deduped)

        # 逐字笛卡尔积（上限 64）
        result: list[list[Syllable]] = [[]]
        for char_syls in candidates:
            if not char_syls:
                char_syls = [
                    Syllable(
                        onset="",
                        nucleus="",
                        coda="",
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                ]
            new_result: list[list[Syllable]] = []
            for combo in result:
                for syl in char_syls:
                    new_result.append(combo + [syl])
            result = new_result
            if len(result) > 64:
                result = result[:64]
        return result

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """返回整行诗的全部读音组合（逐字笛卡尔积）。

        先按 :meth:`tokenize_line` 将行拆为汉字，逐字调用
        :meth:`analyze_word_variants` 得到候选读音，再对整行做笛卡尔积。

        结果上限 64 种组合；超出时按生成顺序保留前 64 种（确定性截断）。

        Args:
            line: 一行诗。

        Returns:
            读音列表；每个元素是一整行的 Syllable 序列（一种读法）。
        """
        chars = self.tokenize_line(line)
        if not chars:
            return []
        word_variants = [self.analyze_word_variants(ch) for ch in chars]

        result: list[list[Syllable]] = [[]]
        for wv in word_variants:
            if not wv:
                wv = [[]]
            new_result: list[list[Syllable]] = []
            for combo in result:
                for variant in wv:
                    new_result.append(combo + variant)
            result = new_result
            if len(result) > 64:
                result = result[:64]
        return result

    def count_syllables(self, text: str) -> int:
        """中文字符数即音节数。

        Args:
            text: 任意文本。

        Returns:
            文本中汉字（CJK 统一表意文字）的数量。
        """
        if not text.strip():
            return 0
        chinese_chars = [
            ch
            for ch in text
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        ]
        return len(chinese_chars)

    def tokenize_line(self, line: str) -> list[str]:
        """逐字切分（仅保留汉字）。

        Args:
            line: 一行诗。

        Returns:
            汉字字符列表。
        """
        return [
            ch
            for ch in line
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        ]
