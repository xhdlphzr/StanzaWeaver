# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""法语音节分析器单元测试（符号层）。"""

from src.prosody.french import FrenchAnalyzer
from src.templates.fr import RondeauTemplate


def test_count_syllables_parle() -> None:
    """验证 count syllables parle。"""
    a = FrenchAnalyzer()
    # par-le：词尾 e 为合法末音节核，计入 -> 2 音节
    assert a.count_syllables("parle") == 2


def test_rhyme_key_parle() -> None:
    """验证 rhyme key parle。"""
    a = FrenchAnalyzer()
    # 末音节核为 e（阴韵），丢弃词尾静音辅音
    assert a.rhyme_key("parle") == "e"


def test_count_syllables_bonjour() -> None:
    """验证 count syllables bonjour。"""
    a = FrenchAnalyzer()
    # bon-jour: 2 音节
    assert a.count_syllables("bonjour") == 2


def test_digraph_eau() -> None:
    """验证 digraph eau。"""
    a = FrenchAnalyzer()
    syls = a.analyze_word("eau")
    assert len(syls) == 1
    assert syls[0].nucleus == "eau"


def test_single_nucleus_words() -> None:
    """验证 single nucleus words。"""
    a = FrenchAnalyzer()
    # FR-1：三合/二合元音视为单一音节核
    assert a.count_syllables("oui") == 1
    assert a.count_syllables("bien") == 1
    assert a.count_syllables("viens") == 1
    assert a.count_syllables("yeux") == 1
    assert a.analyze_word("oui")[0].nucleus == "oui"
    assert a.analyze_word("bien")[0].nucleus == "ien"
    assert a.analyze_word("viens")[0].nucleus == "ien"
    assert a.analyze_word("yeux")[0].nucleus == "yeu"


def test_final_mute_e_counted() -> None:
    """验证 final mute e counted。"""
    a = FrenchAnalyzer()
    # FR-2：词尾 e 作为合法末音节核时必须计入
    assert a.count_syllables("entre") == 2
    assert a.count_syllables("table") == 2
    assert a.count_syllables("maison") == 2
    assert a.count_syllables("petite") == 2
    assert a.count_syllables("porte") == 2


def test_rhyme_key_nasal_merge() -> None:
    """验证 rhyme key nasal merge。"""
    a = FrenchAnalyzer()
    # FR-3：鼻化元音归并 + 丢弃词尾静音辅音
    assert a.rhyme_key("an") == a.rhyme_key("en")
    assert a.rhyme_key("mai") == a.rhyme_key("mais")
    assert a.rhyme_key("lit") == a.rhyme_key("li")
    assert a.rhyme_key("ami") == a.rhyme_key("amis")


def test_syllabify_line_elision() -> None:
    """验证 syllabify line elision。"""
    a = FrenchAnalyzer()
    # FR-4：跨词省音，l'eau 计为 1 音节
    assert a.count_syllables("l'eau") == 1
    assert a.count_syllables("la eau") == 1


def test_rondeau_accepts_uniform_10() -> None:
    """验证 rondeau accepts uniform 10。"""
    from src.prosody.meter_validator import MeterValidator

    template = RondeauTemplate()
    # 每行 10 个 "la"（各 1 音节），共 15 行
    line = " ".join(["la"] * 10)
    poem = [line for _ in range(15)]
    validator = MeterValidator()
    result = validator.validate_count_only(poem, template.to_dict())
    assert not result.errors
    # 区间应允许 8 或 10 音节
    assert template.syllables_per_line[0] == (8, 10)
