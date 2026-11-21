# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""数据化结构规则（src.templates.structural）的单元测试.

覆盖规则数据校验、近体诗各类结构错误分支，并与内置绝句/律诗模板的
原有代码校验结果做一致性对照（保证“数据化携带”不改变判定口径）。
"""

from typing import Any

import pytest

from src.models.syllable import Syllable
from src.prosody.syllable_counter import get_analyzer
from src.templates import _registry, get
from src.templates import structural as st
from src.templates.zh import register_chinese_templates

WUJUE_RULES: dict[str, Any] = {
    "kind": "jinti",
    "attribute": "tone",
    "level_value": "平",
    "oblique_value": "仄",
    "positions": [1, 3],
    "rhyme_lines": [1, 3],
    "optional_first_rhyme": True,
    "forbid_sanpingwei": True,
    "forbid_guping": True,
}


def _syl(tone: str, nucleus: str = "a", coda: str = "") -> Syllable:
    """构造带平仄与韵母的音节."""
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": tone, "stress": "", "length": ""},
    )


def _line(tones: str, nuclei: str | None = None) -> list[Syllable]:
    """按平仄串构造一行音节（韵母可指定）."""
    nucleus_list = list(nuclei) if nuclei else ["a"] * len(tones)
    return [_syl(tone, nucleus_list[i]) for i, tone in enumerate(tones)]


def _line_last(tones: str, last_nucleus: str) -> list[Syllable]:
    """构造一行音节并指定末音节韵母（用于押韵判定）."""
    line = _line(tones)
    line[-1] = _syl(tones[-1], last_nucleus)
    return line


def _poem(*tone_lines: str) -> tuple[list[str], list[list[Syllable]]]:
    """构造诗行文本与音节（文本用于占位，押韵 key 由音节决定）."""
    poem = [f"line{i}" for i in range(len(tone_lines))]
    return poem, [_line(tones) for tones in tone_lines]


# --------------------------------------------------------------------------- #
# 规则数据校验
# --------------------------------------------------------------------------- #
def test_normalize_structural_rules_none() -> None:
    """None 表示没有结构规则."""
    assert st.normalize_structural_rules(None) == (None, None)


def test_normalize_structural_rules_errors() -> None:
    """非法规则数据返回错误."""
    assert st.normalize_structural_rules("bad")[1] is not None
    _, unknown_kind_error = st.normalize_structural_rules({"kind": "x"})
    assert unknown_kind_error is not None
    assert "未知的结构规则类型" in unknown_kind_error
    assert (
        st.normalize_structural_rules({"kind": "jinti"})[1]
        == "结构规则缺少 attribute/level_value/oblique_value"
    )
    assert (
        st.normalize_structural_rules(
            {
                "kind": "jinti",
                "attribute": "tone",
                "level_value": "平",
                "oblique_value": "仄",
                "rhyme_lines": [1],
            }
        )[1]
        == "结构规则缺少 positions/rhyme_lines"
    )
    assert (
        st.normalize_structural_rules(
            {
                "kind": "jinti",
                "attribute": "tone",
                "level_value": "平",
                "oblique_value": "仄",
                "positions": [-1],
                "rhyme_lines": [1],
            }
        )[1]
        is not None
    )


def test_normalize_structural_rules_success() -> None:
    """合法规则被规整（保守布尔值/列表复制）."""
    raw = {
        "kind": "jinti",
        "attribute": "tone",
        "level_value": "平",
        "oblique_value": "仄",
        "positions": (1, 3),
        "rhyme_lines": [1, 3],
        "optional_first_rhyme": 1,
        "forbid_sanpingwei": 0,
    }
    rules, error = st.normalize_structural_rules(raw)
    assert error is None
    assert rules is not None
    assert rules["positions"] == [1, 3]
    assert rules["optional_first_rhyme"] is True
    assert rules["forbid_sanpingwei"] is False
    assert rules["forbid_guping"] is False


def test_as_int_list_invalid_item() -> None:
    """整数列表含非法元素时返回 None."""
    assert st._as_int_list(["a"]) is None
    assert st._as_int_list("x") is None


# --------------------------------------------------------------------------- #
# 近体诗规则各分支
# --------------------------------------------------------------------------- #
def test_check_short_poem_returns_empty() -> None:
    """行数不足直接返回."""
    assert st.check_jinti_rules("zh", ["a"], [_line("平")], WUJUE_RULES) == []


def test_check_skips_empty_lines_and_short_first_line() -> None:
    """空行跳过；首行短于固定位时过滤相应固定位."""
    rules = dict(WUJUE_RULES)
    poem = ["a", "b", "c", "d"]
    syllables = [[], _line("平"), [_syl("平")], _line("平")]
    errors = st.check_jinti_rules("zh", poem, syllables, rules)
    assert isinstance(errors, list)


def test_last_value_empty_line() -> None:
    """空行末音节属性返回空串."""
    assert st._last_value([], "tone") == ""


def test_check_skips_empty_rhyme_line() -> None:
    """韵脚行为空时跳过该行押韵检查."""
    poem = ["a", "b", "c", "d"]
    syllables = [
        _line("仄仄平平仄"),
        [],
        _line("平平平仄仄"),
        _line("仄仄仄平平"),
    ]
    errors = st.check_jinti_rules("zh", poem, syllables, WUJUE_RULES)
    assert isinstance(errors, list)


def test_check_sanpingwei_and_guping() -> None:
    """三平尾与孤平均能检出."""
    # 第1行末三字全平 → 三平尾；第2行平脚且仅一平 → 孤平
    poem, syllables = _poem("仄平平平", "仄仄仄平", "平平平平", "仄仄仄平")
    errors = st.check_jinti_rules("zh", poem, syllables, WUJUE_RULES)
    assert any("三平尾" in e for e in errors)
    assert any("孤平" in e for e in errors)


def test_check_structure_and_rhyme_errors() -> None:
    """出句平脚/对句仄脚/相间/相对/相粘/韵脚非平/押韵不匹配均可检出."""
    # 出句(第3行)平脚、对句(第4行)仄脚
    poem1, syl1 = _poem("仄仄平平仄", "平平仄仄平", "平平仄仄平", "仄仄平平仄")
    errors1 = st.check_jinti_rules("zh", poem1, syl1, WUJUE_RULES)
    assert any("出句" in e for e in errors1)
    assert any("对句" in e for e in errors1)

    # 固定位相间被破坏：第1行第2、4位均为平
    poem2, syl2 = _poem("平平平平仄", "平平仄仄平", "平平平仄仄", "仄仄仄平平")
    errors2 = st.check_jinti_rules("zh", poem2, syl2, WUJUE_RULES)
    assert any("相间" in e for e in errors2)

    # 联内相对被破坏：第1、2行第2位均为平
    poem3, syl3 = _poem("平平平仄仄", "平平仄仄平", "仄仄平平仄", "仄仄仄平平")
    errors3 = st.check_jinti_rules("zh", poem3, syl3, WUJUE_RULES)
    assert any("相对" in e for e in errors3)

    # 联间相粘被破坏：第2行第2位平，第3行第2位仄
    poem4, syl4 = _poem("仄仄平平仄", "平平仄仄平", "仄仄平平仄", "仄仄仄平平")
    errors4 = st.check_jinti_rules("zh", poem4, syl4, WUJUE_RULES)
    assert any("相粘" in e for e in errors4)


def test_check_rhyme_tone_and_mismatch() -> None:
    """韵脚非平声报错；首句入韵时与偶数句不押韵报错."""
    # 第2行韵脚为仄
    poem1, syl1 = _poem("仄仄平平仄", "平平仄仄仄", "平平平仄仄", "仄仄仄平平")
    errors1 = st.check_jinti_rules("zh", poem1, syl1, WUJUE_RULES)
    assert any("韵脚应为'平'" in e for e in errors1)

    # 首句平脚（入韵）但与第2、4行韵母不同
    poem2 = ["a", "b", "c", "d"]
    syllables2 = [
        _line_last("平平仄仄平", "an"),
        _line_last("平平仄仄平", "en"),
        _line_last("平平平仄仄", "an"),
        _line_last("仄仄仄平平", "en"),
    ]
    errors2 = st.check_jinti_rules("zh", poem2, syllables2, WUJUE_RULES)
    assert any("押韵不匹配" in e for e in errors2)

    # 首句平脚且押韵一致 → 通过押韵部分
    syllables3 = [
        _line_last("平平仄仄平", "an"),
        _line_last("平平仄仄平", "an"),
        _line_last("平平平仄仄", "an"),
        _line_last("仄仄仄平平", "an"),
    ]
    errors3 = st.check_jinti_rules(
        "zh",
        poem2,
        syllables3,
        {**WUJUE_RULES, "forbid_sanpingwei": False, "forbid_guping": False},
    )
    assert not any("押韵" in e for e in errors3)


def test_check_unknown_values_are_skipped() -> None:
    """属性值未知时跳过相间/相对/相粘判断."""
    poem = ["a", "b", "c", "d"]
    syllables = [[_syl("")] for _ in range(4)]
    errors = st.check_jinti_rules(
        "zh",
        poem,
        syllables,
        {**WUJUE_RULES, "forbid_sanpingwei": True, "forbid_guping": True},
    )
    # 空属性不产生三平尾/孤平/结构错误，但韵脚无法满足“平”声仍会报错。
    assert errors
    assert all("韵脚" in e for e in errors)


# --------------------------------------------------------------------------- #
# 与内置模板判定一致性
# --------------------------------------------------------------------------- #
POEMS: list[list[str]] = [
    ["远岫依烟岭", "溪流伴月明", "桃红迷柳岸", "古道远山风"],
    ["仄仄平平仄", "平平仄仄平", "平平平仄仄", "仄仄仄平平"],
    ["春江花月风", "秋山夜雪月", "野渡无人灯", "寒梅独映雪"],
    ["国破山河在", "城春草木深", "感时花溅泪", "恨别鸟惊心"],
    ["空山新雨后", "天气晚来秋", "明月松间照", "清泉石上流"],
    ["黄河远上白云间", "一片孤城万仞山", "羌笛何须怨杨柳", "春风不度玉门关"],
]


@pytest.mark.parametrize("key", ["zh_wujue", "zh_qijue"])
def test_parity_with_builtin_short_forms(key: str) -> None:
    """数据化规则与内置绝句模板判定一致."""
    register_chinese_templates()
    template = get(key)
    analyzer = get_analyzer("zh")
    rules = st.normalize_structural_rules(template.structural_rules)[0]
    assert rules is not None
    for poem in POEMS:
        expected = 5 if key == "zh_wujue" else 7
        if any(len(line) != expected for line in poem):
            continue
        syllables = [analyzer.analyze_line_variants(line)[0] for line in poem]
        builtin = template.validate_full(poem, syllables)
        dataized = st.check_jinti_rules("zh", poem, syllables, rules)
        assert (not builtin) == (not dataized), (poem, builtin, dataized)


@pytest.mark.parametrize("key", ["zh_wulv", "zh_qilv"])
def test_parity_with_builtin_regular_forms(key: str) -> None:
    """数据化规则与内置律诗模板的韵脚/三平尾/孤平判定一致（样例集合）."""
    register_chinese_templates()
    template = get(key)
    rules = st.normalize_structural_rules(template.structural_rules)[0]
    assert rules is not None
    assert rules["rhyme_lines"] == [1, 3, 5, 7]
    analyzer = get_analyzer("zh")
    poem = [
        "空山新雨后",
        "天气晚来秋",
        "明月松间照",
        "清泉石上流",
        "竹喧归浣女",
        "莲动下渔舟",
        "随意春芳歇",
        "王孙自可留",
    ]
    syllables = [analyzer.analyze_line_variants(line)[0] for line in poem]
    builtin = template.validate_full(poem, syllables)
    dataized = st.check_jinti_rules("zh", poem, syllables, rules)
    assert (not builtin) == (not dataized), (builtin, dataized)


def test_structural_rules_registered_for_jinti_templates() -> None:
    """绝句/律诗模板均声明了数据化结构规则与标准位次."""
    register_chinese_templates()
    for key, lines, positions in [
        ("zh_wujue", 4, [1, 3]),
        ("zh_qijue", 4, [1, 3, 5]),
        ("zh_wulv", 8, [1, 3]),
        ("zh_qilv", 8, [1, 3, 5]),
    ]:
        template = get(key)
        rules, error = st.normalize_structural_rules(template.structural_rules)
        assert error is None and rules is not None
        assert template.lines == lines
        assert rules["positions"] == positions


def test_special_rules_are_strings() -> None:
    """内置模板的 special_rules 均为字符串元组（前端可展示）."""
    for template in _registry.values():
        assert isinstance(template.special_rules, tuple)
        assert all(isinstance(rule, str) for rule in template.special_rules)
