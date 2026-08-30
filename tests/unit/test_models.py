# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""符号层（src.models）单元测试：Syllable 与 Word 数据模型。"""

from src.models.syllable import Syllable
from src.models.word import Word


def _syl(
    onset: str = "",
    nucleus: str = "a",
    coda: str = "",
    tone: str = "",
    stress: str = "",
    length: str = "",
) -> Syllable:
    """syl。"""
    return Syllable(
        onset=onset,
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": tone, "stress": stress, "length": length},
    )


def test_syllable_text_concatenates() -> None:
    """验证 syllable text concatenates。"""
    s = Syllable(onset="str", nucleus="IY", coda="T")
    assert s.text == "strIYT"


def test_syllable_text_empty() -> None:
    """验证 syllable text empty。"""
    assert Syllable().text == ""


def test_syllable_match_constraint_empty_is_true() -> None:
    """验证 syllable match constraint empty is true。"""
    assert _syl().match_constraint({}) is True


def test_syllable_match_constraint_onset() -> None:
    """验证 syllable match constraint onset。"""
    s = _syl(onset="zh")
    assert s.match_constraint({"onset": "zh"}) is True
    assert s.match_constraint({"onset": "ch"}) is False


def test_syllable_match_constraint_nucleus() -> None:
    """验证 syllable match constraint nucleus。"""
    s = _syl(nucleus="iao")
    assert s.match_constraint({"nucleus": "iao"}) is True
    assert s.match_constraint({"nucleus": "a"}) is False


def test_syllable_match_constraint_coda() -> None:
    """验证 syllable match constraint coda。"""
    s = _syl(coda="ng")
    assert s.match_constraint({"coda": "ng"}) is True
    assert s.match_constraint({"coda": "n"}) is False


def test_syllable_match_constraint_attributes() -> None:
    """验证 syllable match constraint attributes。"""
    s = _syl(tone="平", stress="heavy", length="long")
    assert s.match_constraint({"attributes": {"tone": "平"}}) is True
    assert s.match_constraint({"attributes": {"tone": "仄"}}) is False
    assert s.match_constraint({"attributes": {"stress": "heavy"}}) is True
    assert s.match_constraint({"attributes": {"length": "short"}}) is False


def test_syllable_match_constraint_attributes_non_dict() -> None:
    """验证 syllable match constraint attributes non dict。"""
    # attributes 约束不是 dict 时视为无附加约束，应忽略并返回 True（覆盖 line 60）
    s = _syl(tone="平")
    assert s.match_constraint({"attributes": "not-a-dict"}) is True


def test_syllable_to_dict() -> None:
    """验证 syllable to dict。"""
    s = _syl(onset="zh", nucleus="a", coda="ng", tone="平", stress="", length="short")
    assert s.to_dict() == {
        "onset": "zh",
        "nucleus": "a",
        "coda": "ng",
        "attributes": {"tone": "平", "stress": "", "length": "short"},
    }


def test_syllable_from_dict() -> None:
    """验证 syllable from dict。"""
    d = {
        "onset": "str",
        "nucleus": "IY",
        "coda": "T",
        "attributes": {"tone": "仄", "stress": "light", "length": "long"},
    }
    s = Syllable.from_dict(d)
    assert s.onset == "str"
    assert s.nucleus == "IY"
    assert s.coda == "T"
    assert s.attributes == {"tone": "仄", "stress": "light", "length": "long"}


def test_syllable_from_dict_attributes_non_dict() -> None:
    """验证 syllable from dict attributes non dict。"""
    # attributes 不是 dict 时回退为空属性（覆盖 line 98）
    s = Syllable.from_dict({"attributes": "bad", "onset": "b"})
    assert s.attributes == {"tone": "", "stress": "", "length": ""}
    assert s.onset == "b"


def test_word_syllable_count() -> None:
    """验证 word syllable count。"""
    w = Word(text="X", language="en", syllables=[_syl(), _syl(), _syl()])
    assert w.syllable_count == 3
    assert Word(text="X", language="en").syllable_count == 0


def test_word_to_dict_with_syllables() -> None:
    """验证 word to dict with syllables。"""
    w = Word(
        text="ZHONG",
        language="zh",
        syllables=[_syl(onset="zh", nucleus="o", tone="平")],
        meaning="中",
    )
    assert w.to_dict() == {
        "text": "ZHONG",
        "language": "zh",
        "syllables": [
            {
                "onset": "zh",
                "nucleus": "o",
                "coda": "",
                "attributes": {"tone": "平", "stress": "", "length": ""},
            }
        ],
        "meaning": "中",
    }


def test_word_to_dict_empty_syllables() -> None:
    """验证 word to dict empty syllables。"""
    w = Word(text="X", language="en")
    assert w.to_dict()["syllables"] == []


def test_word_from_dict_with_dict_syllables() -> None:
    """验证 word from dict with dict syllables。"""
    d = {
        "text": "AQUA",
        "language": "la",
        "syllables": [
            {"onset": "", "nucleus": "a"},
            {"onset": "qu", "nucleus": "a"},
        ],
        "meaning": "水",
    }
    w = Word.from_dict(d)
    assert w.text == "AQUA"
    assert w.language == "la"
    assert len(w.syllables) == 2
    assert w.syllables[0].nucleus == "a"
    assert w.syllables[1].onset == "qu"
    assert w.meaning == "水"


def test_word_from_dict_with_syllable_instances() -> None:
    """验证 word from dict with syllable instances。"""
    d = {
        "text": "HI",
        "language": "en",
        "syllables": [_syl(onset="h", nucleus="a"), _syl(onset="", nucleus="i")],
        "meaning": "",
    }
    w = Word.from_dict(d)
    assert w.syllables[0].onset == "h"
    assert w.syllables[1].nucleus == "i"


def test_word_from_dict_skips_non_syllable_non_dict() -> None:
    """验证 word from dict skips non syllable non dict。"""
    # 列表中既非 Syllable 也非 dict 的元素应被跳过（循环非空但不命中任一分支）
    d = {"text": "X", "language": "en", "syllables": [None, 123]}
    w = Word.from_dict(d)
    assert w.syllables == []


def test_word_from_dict_missing_fields_default_empty() -> None:
    """验证 word from dict missing fields default empty。"""
    w = Word.from_dict({})
    assert w.text == ""
    assert w.language == ""
    assert w.syllables == []
    assert w.meaning == ""
