# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""拉丁语音节分析器单元测试（符号层）。"""

from src.prosody.latin import LatinAnalyzer


def test_count_syllables_amor() -> None:
    a = LatinAnalyzer()
    assert a.count_syllables("amor") == 2


def test_mutua_cum_liquida_merges() -> None:
    a = LatinAnalyzer()
    # patris: p+t+r 构成 muta cum liquida，仅算一个辅音位 -> 全作 "a" 的 onset
    syls = a.analyze_word("patris")
    assert len(syls) == 2
    assert syls[0].onset == "ptr"
    assert syls[0].nucleus == "a"


def test_diphthong_is_long() -> None:
    a = LatinAnalyzer()
    # au 为双元音 -> 长音
    syls = a.analyze_word("aurum")
    assert syls[0].nucleus == "au"
    assert syls[0].attributes["length"] == "long"


def test_consonantal_u() -> None:
    a = LatinAnalyzer()
    # qu 中 u 为辅音性，不构成独立音节
    syls = a.analyze_word("aqua")
    assert len(syls) == 2
    assert syls[0].onset == "qu"


def test_leading_consonant_count() -> None:
    a = LatinAnalyzer()
    # muta cum liquida 仅算 1
    assert a._leading_consonant_count("tr") == 1
    # x 计为 2 个辅音位
    assert a._leading_consonant_count("tx") == 3
    # 普通塞音为 1
    assert a._leading_consonant_count("patris") == 1


def test_analyze_line_cross_word_length() -> None:
    a = LatinAnalyzer()
    # arma(2) + virum(2) = 4 音节
    assert len(a.analyze_line("arma virum")) == 4
