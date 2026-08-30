# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""中文音节分析器单元测试（符号层）。"""

from src.models.syllable import Syllable
from src.prosody.chinese import ChineseAnalyzer
from src.templates.zh import QijueTemplate, WujueTemplate


def _mk_line(pairs: list[tuple[str, str]]) -> list[Syllable]:
    """由 (平仄, 韵母) 列表构造一行 Syllable。

    Args:
        pairs: 每元素为 (tone, final)，final 直接作为韵腹（无韵尾）。

    Returns:
        Syllable 列表。
    """
    return [
        Syllable(
            onset="",
            nucleus=final,
            coda="",
            attributes={"tone": tone, "stress": "", "length": ""},
        )
        for tone, final in pairs
    ]


def test_count_syllables_counts_cjk_chars() -> None:
    """验证 count syllables counts cjk chars。"""
    a = ChineseAnalyzer()
    assert a.count_syllables("床前明月光") == 5
    assert a.count_syllables("  静夜思  ") == 3
    assert a.count_syllables("") == 0


def test_analyze_word_single_char_parts() -> None:
    """验证 analyze word single char parts。"""
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
    """验证 analyze word tone ping ze。"""
    a = ChineseAnalyzer()
    # 去 (qù, 4声) -> 仄
    assert a.analyze_word("去")[0].attributes["tone"] == "仄"
    # 床 (chuáng, 2声) -> 平
    assert a.analyze_word("床")[0].attributes["tone"] == "平"


def test_tokenize_line_keeps_only_cjk() -> None:
    """验证 tokenize line keeps only cjk。"""
    a = ChineseAnalyzer()
    assert a.tokenize_line("床前，明月光！") == ["床", "前", "明", "月", "光"]


def test_analyze_word_variants_polyphonic() -> None:
    """验证 analyze word variants polyphonic。"""
    a = ChineseAnalyzer()
    # 中 为多音字：zhōng(平) / zhòng(仄)
    variants = a.analyze_word_variants("中")
    tones = {s.attributes["tone"] for v in variants for s in v}
    assert "平" in tones
    assert "仄" in tones
    # 返回的是整词读音列表，每个元素为整词 Syllable 序列
    assert all(isinstance(v, list) for v in variants)
    assert all(len(v) == 1 for v in variants)


def test_neutral_tone_maps_to_ping() -> None:
    """验证 neutral tone maps to ping。"""
    a = ChineseAnalyzer()
    # 的 为轻声，应归为平声
    assert a.analyze_word("的")[0].attributes["tone"] == "平"


def test_sanpingwei_flagged_sanzewei_removed() -> None:
    """验证 sanpingwei flagged sanzewei removed。"""
    tpl = WujueTemplate()
    # 第2行为三平尾；末三字全平应被标记
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("平", "ang")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ang")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("三平尾" in e for e in errors)
    # 三仄尾已不再是禁忌，不应报告
    assert not any("三仄尾" in e for e in errors)


def test_sanzewei_no_longer_error() -> None:
    """验证 sanzewei no longer error。"""
    tpl = WujueTemplate()
    # 末三字全仄的合法五言绝句：不应报三仄尾
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "ang")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ang")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert not any("三仄尾" in e for e in errors)
    # 该诗整体合律（无其他错误）
    assert errors == []


def test_guping_still_reported() -> None:
    """验证 guping still reported。"""
    tpl = QijueTemplate()
    # 孤平保留判定：第4句为孤平句（仄仄仄仄平，全句仅韵脚一平），应仍报告孤平
    poem = ["", "", "", ""]
    syllables = [
        _mk_line(
            [
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "ang"),
            ]
        ),
        _mk_line(
            [
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "ang"),
            ]
        ),
        _mk_line(
            [
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "a"),
                ("平", "a"),
                ("仄", "a"),
            ]
        ),
        _mk_line(
            [
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("仄", "a"),
                ("平", "ang"),
            ]
        ),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("孤平" in e for e in errors)


def test_rhyme_tongyun_ing_ong_fail() -> None:
    """验证 rhyme tongyun ing ong fail。"""
    tpl = WujueTemplate()
    # ing(庚) 与 ong(东) 不同部，应判不押韵
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "ing")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "ong")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert errors, "ing(庚) 与 ong(东) 不同部，应报押韵错误"


def test_rhyme_tongyun_i_u_fail() -> None:
    """验证 rhyme tongyun i u fail。"""
    tpl = WujueTemplate()
    # i(齐) 与 u(姑) 不同部，应判不押韵
    poem = ["", "", "", ""]
    syllables = [
        _mk_line([("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "a"), ("仄", "a")]),
        _mk_line([("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a"), ("平", "i")]),
        _mk_line([("平", "a"), ("平", "a"), ("平", "a"), ("仄", "a"), ("仄", "a")]),
        _mk_line([("仄", "a"), ("仄", "a"), ("仄", "a"), ("平", "a"), ("平", "u")]),
    ]
    errors = tpl.validate_full(poem, syllables)
    assert any("押韵" in e for e in errors)
