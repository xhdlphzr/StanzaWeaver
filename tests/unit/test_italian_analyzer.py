# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""意大利语音节分析器单元测试（符号层）。"""

from src.prosody.italian import ItalianAnalyzer


def test_count_amor() -> None:
    a = ItalianAnalyzer()
    # a-mor: 2 音节，末音节重读（辅音收尾）
    assert a.count_syllables("amor") == 2
    syls = a.analyze_word("amor")
    assert syls[-1].attributes["stress"] == "heavy"


def test_count_citta() -> None:
    a = ItalianAnalyzer()
    # ci-ttà: 2 音节，末音节重读（词尾重音元音）
    assert a.count_syllables("città") == 2


def test_no_sinalefe_when_prev_coda() -> None:
    a = ItalianAnalyzer()
    # amor 末音节韵尾 r 非空 -> 不与 "e" 并读
    assert a.count_syllables("amor e") == 3


def test_sinalefe_merges_cross_word_vowels() -> None:
    a = ItalianAnalyzer()
    # poeti 末元音 i 与 e 并读为一个音节: 3 而非 4
    assert a.count_syllables("poeti e") == 3
