# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""中文音节分析器单元测试（符号层）。"""

from src.prosody.chinese import ChineseAnalyzer


def test_count_syllables_counts_cjk_chars() -> None:
    a = ChineseAnalyzer()
    assert a.count_syllables("床前明月光") == 5
    assert a.count_syllables("  静夜思  ") == 3
    assert a.count_syllables("") == 0


def test_analyze_word_single_char_parts() -> None:
    a = ChineseAnalyzer()
    # 光 guāng: 声母 g, 韵腹 a, 韵尾 ng, 一声(平)
    syls = a.analyze_word("光")
    assert len(syls) == 1
    s = syls[0]
    assert s.onset == "g"
    assert s.nucleus == "ua"
    assert s.coda == "ng"
    assert s.attributes["tone"] == "平"


def test_analyze_word_tone_ping_ze() -> None:
    a = ChineseAnalyzer()
    # 去 (qù, 4声) -> 仄
    assert a.analyze_word("去")[0].attributes["tone"] == "仄"
    # 床 (chuáng, 2声) -> 平
    assert a.analyze_word("床")[0].attributes["tone"] == "平"


def test_tokenize_line_keeps_only_cjk() -> None:
    a = ChineseAnalyzer()
    assert a.tokenize_line("床前，明月光！") == ["床", "前", "明", "月", "光"]
