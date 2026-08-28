# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Syllable 数据模型单元测试（符号层）。"""

from src.models.syllable import Syllable


def test_text_concatenates_parts() -> None:
    s = Syllable(onset="zh", nucleus="a", coda="ng")
    assert s.text == "zhang"


def test_match_constraint_empty_always_passes() -> None:
    s = Syllable(onset="b", nucleus="a", coda="")
    assert s.match_constraint({}) is True


def test_match_constraint_onset_mismatch() -> None:
    s = Syllable(onset="zh", nucleus="a", coda="")
    assert s.match_constraint({"onset": "z"}) is False
    assert s.match_constraint({"onset": "zh"}) is True


def test_match_constraint_nucleus_and_coda() -> None:
    s = Syllable(onset="", nucleus="iao", coda="ng")
    assert s.match_constraint({"nucleus": "iao", "coda": "ng"}) is True
    assert s.match_constraint({"nucleus": "ia"}) is False
    assert s.match_constraint({"coda": "n"}) is False


def test_match_constraint_attributes() -> None:
    s = Syllable(attributes={"tone": "平", "stress": "", "length": ""})
    assert s.match_constraint({"attributes": {"tone": "平"}}) is True
    assert s.match_constraint({"attributes": {"tone": "仄"}}) is False


def test_to_dict_from_dict_roundtrip() -> None:
    s = Syllable(onset="x", nucleus="ü", coda="", attributes={"tone": "仄"})
    d = s.to_dict()
    # to_dict 原样输出存储的属性（不补默认空值）
    assert d == {
        "onset": "x",
        "nucleus": "ü",
        "coda": "",
        "attributes": {"tone": "仄"},
    }
    # from_dict 会回补缺失的默认属性
    restored = Syllable.from_dict(d)
    assert restored.onset == "x"
    assert restored.nucleus == "ü"
    assert restored.attributes["tone"] == "仄"
    assert restored.attributes["stress"] == ""
    assert restored.attributes["length"] == ""
