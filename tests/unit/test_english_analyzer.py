# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""英语音节分析器单元测试（符号层，离线播种 CMUdict）。"""

from unittest import mock

from src.prosody.english import EnglishAnalyzer


def test_parse_phones_single_syllable() -> None:
    """验证 parse phones single syllable。"""
    a = EnglishAnalyzer()
    # test /tɛst/: onset t, nucleus ɛ, coda st, 主重音
    syls = a._parse_phones(["T", "EH1", "S", "T"])
    assert len(syls) == 1
    s = syls[0]
    assert s.onset == "T"
    assert s.nucleus == "EH"
    assert s.coda == "ST"
    assert s.attributes["stress"] == "heavy"


def test_parse_phones_two_syllables() -> None:
    """验证 parse phones two syllables。"""
    a = EnglishAnalyzer()
    # happy /hæpi/: 前重后轻
    syls = a._parse_phones(["HH", "AE1", "P", "IY0"])
    assert len(syls) == 2
    assert syls[0].onset == "HH"
    assert syls[0].nucleus == "AE"
    assert syls[0].coda == "P"
    assert syls[0].attributes["stress"] == "heavy"
    assert syls[1].nucleus == "IY"
    assert syls[1].attributes["stress"] == "light"


def test_analyze_word_seeded() -> None:
    """验证 analyze word seeded。"""
    a = EnglishAnalyzer()
    syls = a.analyze_word("light")
    assert len(syls) == 1
    assert syls[0].nucleus == "AY"
    assert syls[0].attributes["stress"] == "heavy"


def test_fallback_analyze_unknown_word() -> None:
    """验证 fallback analyze unknown word。"""
    a = EnglishAnalyzer()
    syls = a._fallback_analyze("rhythm")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"
    assert syls[0].attributes["stress"] == "light"


def test_rhyme_tail_seeded() -> None:
    """验证 rhyme tail seeded。"""
    a = EnglishAnalyzer()
    assert a.rhyme_tail("light") == "AY1 T"
    # 未知词无发音，不应作为韵脚 key
    assert a.rhyme_tail("zzznotaword") is None


def test_count_syllables_offline() -> None:
    """验证 count syllables 离线回退（不依赖真实词库 / cmudict）。

    强制发音查询返回空，使分析器走启发式回退，结果纯由正则可确定：
    "rhythm"（y 计 1）+ "xyz"（y 计 1）= 2。
    """
    a = EnglishAnalyzer()
    with mock.patch.object(EnglishAnalyzer, "_get_pronunciations", return_value=[]):
        assert a.count_syllables("rhythm xyz") == 2
