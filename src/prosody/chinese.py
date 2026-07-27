# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from pypinyin import pinyin, Style

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

_FINAL_TO_PARTS = {
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

_PING_TONES = {"1", "2"}
_ZE_TONES = {"3", "4"}


def _split_final(final_str: str) -> tuple[str, str]:
    if not final_str:
        return "", ""
    tone_char = final_str[-1]
    if tone_char.isdigit():
        base = final_str[:-1]
    else:
        base = final_str
        tone_char = ""
    base_lower = base.lower()
    nucleus, coda = _FINAL_TO_PARTS.get(base_lower, (base, ""))
    return nucleus, coda


def _tone_to_pingze(tone_str: str) -> str:
    if not tone_str:
        return ""
    t = tone_str[-1] if tone_str[-1].isdigit() else tone_str
    if t in _PING_TONES:
        return "平"
    if t in _ZE_TONES:
        return "仄"
    return ""


class ChineseAnalyzer(SyllableAnalyzer):
    language = "zh"

    def analyze_word(self, word: str) -> list[Syllable]:
        if not word:
            return []
        results = []
        initials_list = pinyin(
            word, style=Style.INITIALS, strict=False, heteronym=False
        )
        finals_list = pinyin(
            word, style=Style.FINALS_TONE3, strict=False, heteronym=False
        )

        for initials, finals in zip(initials_list, finals_list):
            onset = initials[0] if initials[0] else ""
            final_raw = finals[0] if finals[0] else ""
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
        if not text.strip():
            return 0
        chinese_chars = [
            ch
            for ch in text
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        ]
        return len(chinese_chars)

    def tokenize_line(self, line: str) -> list[str]:
        return [
            ch
            for ch in line
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        ]
