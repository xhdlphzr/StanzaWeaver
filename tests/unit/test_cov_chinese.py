# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""中文音节分析器覆盖补全测试（针对 100% 行覆盖的残留分支）。"""

from unittest.mock import patch

from pypinyin import Style

from src.prosody.chinese import (
    ChineseAnalyzer,
    _split_final,
    _tone_to_pingze,
)


def test_split_final_empty_returns_empty_pair() -> None:
    """验证 _split_final 空输入返回 ("", "")。"""
    assert _split_final("") == ("", "")


def test_tone_to_pingze_empty_returns_ping() -> None:
    """验证 _tone_to_pingze 空串归为平声。"""
    assert _tone_to_pingze("") == "平"


def test_tone_to_pingze_unusual_digit_returns_ping() -> None:
    """验证 _tone_to_pingze 非常规数字（如 5 声）归为平声。"""
    assert _tone_to_pingze("iao5") == "平"
    assert _tone_to_pingze("x5") == "平"


def test_analyze_word_empty_returns_empty() -> None:
    """验证 analyze_word 空输入返回空列表（line 173）。"""
    a = ChineseAnalyzer()
    assert a.analyze_word("") == []


def test_analyze_word_variants_empty_returns_empty() -> None:
    """验证 analyze_word_variants 空输入返回空列表（line 191）。"""
    a = ChineseAnalyzer()
    assert a.analyze_word_variants("") == []


def test_analyze_word_variants_fallback_empty_char_syls() -> None:
    """验证某字无候选读音时补空 Syllable（line 239）。

    通过 mock pinyin，使某个字的 finals 候选为空，使内层双循环
    不产出任何 Syllable，从而触发 ``if not char_syls`` 回退。
    """
    a = ChineseAnalyzer()
    initials_list: list[list[str]] = [["x"]]
    finals_list: list[list[str]] = [[]]

    def _pinyin(
        word: str,
        style: Style = Style.NORMAL,
        strict: bool = True,
        heteronym: bool = False,
    ) -> list[list[str]]:
        """mock 的 pinyin 替身：按 style 返回预设的 initials/finals 列表。"""
        if style == Style.INITIALS:
            return initials_list
        return finals_list

    with patch("src.prosody.chinese.pinyin", side_effect=_pinyin):
        variants = a.analyze_word_variants("中")
    # 回退补了一个空 Syllable，故得到一种读音
    assert len(variants) == 1
    assert variants[0][0].nucleus == ""


def test_analyze_word_variants_truncates_to_64() -> None:
    """验证笛卡尔积超过 64 时按序截断（line 253）。

    通过 mock pinyin，使单个字产生 65 个候选读音（不同韵腹），
    触发 ``if len(result) > 64`` 截断到前 64 种。
    """
    a = ChineseAnalyzer()
    finals: list[str] = [f"{i}1" for i in range(65)]
    initials_list: list[list[str]] = [["x"]]
    finals_list: list[list[str]] = [finals]

    def _pinyin(
        word: str,
        style: Style = Style.NORMAL,
        strict: bool = True,
        heteronym: bool = False,
    ) -> list[list[str]]:
        """mock 的 pinyin 替身：按 style 返回预设的 initials/finals 列表。"""
        if style == Style.INITIALS:
            return initials_list
        return finals_list

    with patch("src.prosody.chinese.pinyin", side_effect=_pinyin):
        variants = a.analyze_word_variants("中")
    assert len(variants) == 64


def test_analyze_line_variants_empty_word_variant() -> None:
    """验证某字读音为空时回退为 [[]]（line 278）。

    通过 mock ``analyze_word_variants`` 返回空列表，使 per-char 循环中
    ``if not wv: wv = [[]]`` 分支被执行。
    """
    a = ChineseAnalyzer()
    with patch.object(ChineseAnalyzer, "analyze_word_variants", return_value=[]):
        variants = a.analyze_line_variants("中")
    # 回退 [[]] 与初始 [[]] 笛卡尔积仍为 [[]]
    assert variants == [[]]
