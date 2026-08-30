# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""统一音节计数 / 整行分析入口单元测试（符号层）。"""

import pytest

from src.models.syllable import Syllable
from src.prosody.base import SyllableAnalyzer
from src.prosody.syllable_counter import (
    analyze_line,
    count_syllables,
    get_analyzer,
    register_analyzer,
)


def test_count_syllables_zh() -> None:
    """验证 count syllables zh。"""
    assert count_syllables("床前明月光", "zh") == 5


def test_analyze_line_zh_syllables() -> None:
    """验证 analyze line zh syllables。"""
    syls = analyze_line("光", "zh")
    assert len(syls) == 1
    assert syls[0].nucleus == "ua"


def test_analyze_line_it_sinalefe() -> None:
    """验证 analyze line it sinalefe。"""
    # poeti e: 跨词元音并读 -> 3 音节
    assert count_syllables("poeti e", "it") == 3


def test_analyze_line_la_routes() -> None:
    """验证 analyze line la routes。"""
    syls = analyze_line("amor", "la")
    assert all(isinstance(s, Syllable) for s in syls)
    assert len(syls) == 2


def test_get_analyzer_unknown_language() -> None:
    """验证 get analyzer unknown language。"""
    with pytest.raises(ValueError):
        get_analyzer("xx")


def test_register_analyzer_override() -> None:
    """验证 register analyzer override。"""

    class Dummy(SyllableAnalyzer):
        """用于测试 register 覆盖的桩分析器。"""

        language = "dummy"

        def analyze_word(self, word: str) -> list[Syllable]:
            """返回空音节列表。

            Args:
                word: 待分析单词。

            Returns:
                空列表。
            """
            return []

        def count_syllables(self, text: str) -> int:
            """count syllables。"""
            return 0

    register_analyzer("dummy", Dummy())
    assert isinstance(get_analyzer("dummy"), Dummy)
    # 再次注册覆盖同样可行（不影响其他测试：无其它用例使用 "dummy"）
    register_analyzer("dummy", Dummy())
