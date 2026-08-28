# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""法语音节分析器单元测试（符号层）。"""

from src.prosody.french import FrenchAnalyzer


def test_count_syllables_parle() -> None:
    a = FrenchAnalyzer()
    # parle -> 静音 e 去除后 "parl": 1 音节
    assert a.count_syllables("parle") == 1


def test_rhyme_key_parle() -> None:
    a = FrenchAnalyzer()
    # 末音节韵腹 a + 韵尾 rl
    assert a.rhyme_key("parle") == "arl"


def test_count_syllables_bonjour() -> None:
    a = FrenchAnalyzer()
    # bon-jour: 2 音节
    assert a.count_syllables("bonjour") == 2


def test_digraph_eau() -> None:
    a = FrenchAnalyzer()
    syls = a.analyze_word("eau")
    assert len(syls) == 1
    assert syls[0].nucleus == "eau"
