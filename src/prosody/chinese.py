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

    Args:
        tone_str: 带声调数字的韵母串（如 "iao3"）或纯标签。

    Returns:
        "平"、"仄" 或 ""（轻声/未知）。
    """
    if not tone_str:
        return ""
    t = tone_str[-1] if tone_str[-1].isdigit() else tone_str
    if t in _PING_TONES:
        return "平"
    if t in _ZE_TONES:
        return "仄"
    return ""


class ChineseAnalyzer(SyllableAnalyzer):
    """中文音节分析器：逐字输出声母/韵腹/韵尾 + 平仄。

    analyze_word 接受任意长度文本（含整行），pypinyin 会按短语上下文
    自动选择多音字的正确读音。
    """

    language = "zh"

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析中文文本（可多字）的音节。

        Args:
            word: 中文文本，如 "弹琴" 或整行诗。

        Returns:
            每字一个 Syllable（平仄标在 attributes["tone"]）。
        """
        if not word:
            return []
        results: list[Syllable] = []
        initials_list = pinyin(
            word, style=Style.INITIALS, strict=False, heteronym=False
        )
        finals_list = pinyin(
            word, style=Style.FINALS_TONE3, strict=False, heteronym=False
        )

        for initials, finals in zip(initials_list, finals_list):
            onset = str(initials[0]) if initials[0] else ""
            final_raw = str(finals[0]) if finals[0] else ""
            nucleus, coda = _split_final(final_raw)
            tone_label = _tone_to_pingze(final_raw)

            results.append(
                Syllable(
                    onset=onset,
                    nucleus=nucleus,
                    coda=coda,
                    attributes={"tone": tone_label, "stress": "", "length": ""},
                )
            )
        return results

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
