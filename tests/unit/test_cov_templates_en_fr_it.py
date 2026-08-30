# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""补充单元测试：将 src/templates 四个模块（__init__/en/fr/it）行覆盖拉满。

本文件仅新增测试用例，不修改任何源代码，也不修改既有测试文件。
通过构造最小桩模板、构造特定输入以及按需打桩（mock）英语分析器，
触发 en/fr/it/__init__ 中尚未覆盖的分支。
"""

from collections.abc import Generator
from typing import ClassVar

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.models.syllable import Syllable
from src.templates import (
    ConstraintTable,
    PoetryTemplate,
    _make_syl,
    format_count,
    list_all,
    list_dicts,
)
from src.templates import en as en_module
from src.templates import fr as fr_module
from src.templates.en import (
    HeroicCoupletTemplate,
    ShakespeareSonnetTemplate,
    VillanelleTemplate,
    _en_rhyme_key,
)
from src.templates.en import (
    _check_rhyme_group as en_check_rhyme_group,
)
from src.templates.en import (
    _check_stress_count as en_check_stress_count,
)
from src.templates.en import (
    _en_last_word as en_last_word,
)
from src.templates.fr import (
    BalladeTemplate,
    RondeauTemplate,
    TrioletTemplate,
)
from src.templates.fr import (
    _check_rhyme_group as fr_check_rhyme_group,
)
from src.templates.fr import (
    _fr_last_word as fr_last_word,
)
from src.templates.it import (
    CanzoneTemplate,
    OttavaRimaTemplate,
    TerzaRimaTemplate,
)


class _BareTemplate(PoetryTemplate):
    """不覆盖任何方法的基类桩（用于覆盖基类默认实现分支）。"""


class _ConstraintTemplate(PoetryTemplate):
    """带逐位约束（含 onset/nucleus/coda 与 attributes）的桩模板。"""

    name = "测试约束模板"
    language = "xx"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [2]
    rule_description = "行覆盖用规则描述"

    def get_syllable_constraints(self) -> ConstraintTable:
        """返回含 onset/nucleus/coda 与 attributes 的约束表。"""
        return [
            [
                {
                    "onset": "b",
                    "nucleus": "a",
                    "coda": "t",
                    "attributes": {
                        "tone": "xx",
                        "stress": "heavy",
                        "length": "",
                    },
                }
            ]
        ]


@pytest.fixture()
def registry_snapshot() -> Generator[None, None, None]:
    """测试前后恢复全局 _registry，避免污染其他用例。

    Yields:
        无（恢复操作在 yield 后执行）。
    """
    from src.templates import _registry

    saved: dict[str, PoetryTemplate] = dict(_registry)
    yield
    _registry.clear()
    _registry.update(saved)


def test_base_get_syllable_constraints_returns_none() -> None:
    """基类默认 get_syllable_constraints 应返回 None（覆盖 __init__ 41）。"""
    assert _BareTemplate().get_syllable_constraints() is None


def test_base_validate_full_returns_empty() -> None:
    """基类默认 validate_full 应返回空列表（覆盖 __init__ 55）。"""
    assert _BareTemplate().validate_full([], []) == []


def test_describe_with_constraints_covers_branches() -> None:
    """describe 应进入逐位约束拼接分支（覆盖 __init__ 83-98）。"""
    desc = _ConstraintTemplate().describe()
    assert "声母=b" in desc
    assert "韵母=a" in desc
    assert "韵尾=t" in desc
    assert "tone=xx" in desc


def test_format_count_tuple_branch() -> None:
    """format_count 对 (min,max) 区间应返回 'x-y'（覆盖 __init__ 128）。"""
    assert format_count((8, 10)) == "8-10"


def test_format_count_int_branch() -> None:
    """format_count 对 int 应返回其字符串形式（覆盖 __init__ 129）。"""
    assert format_count(5) == "5"


def test_list_all_returns_registered(registry_snapshot: None) -> None:
    """list_all 应返回全部已注册模板（覆盖 __init__ 153）。"""
    from src.templates import _registry

    _registry.clear()
    inst = _BareTemplate()
    _registry["cov_test"] = inst
    assert inst in list_all()


def test_list_dicts_label_and_fallback(registry_snapshot: None) -> None:
    """list_dicts 应同时覆盖已知语言标签与未知语言回退。"""
    from src.templates import _registry

    _registry.clear()
    _registry["cov_en"] = ShakespeareSonnetTemplate()
    _registry["cov_xx"] = _ConstraintTemplate()
    dicts = list_dicts()
    names = [d["display_name"] for d in dicts]
    assert any("英语" in n for n in names)
    assert any("（xx）" in n for n in names)


def test_en_make_syl_non_dict_attributes() -> None:
    """_make_syl 接收非 dict 的 attributes 时应回退为空字典（覆盖 en 32）。"""
    syl = _make_syl(attributes="not-a-dict")
    assert syl["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_en_last_word_empty() -> None:
    """_last_word 对空行应返回空串（覆盖 en 59）。"""
    assert en_last_word("   ") == ""


def test_en_rhyme_key_empty_returns_none() -> None:
    """_en_rhyme_key 对空行应返回 None（覆盖 en 77）。"""
    assert _en_rhyme_key("") is None


def test_en_check_stress_count_too_few() -> None:
    """_check_stress_count 应在重音不足时追加错误（覆盖 en 98）。"""
    errors: list[str] = []
    light = Syllable(attributes={"stress": "light"})
    en_check_stress_count(["a line"], [[light]], 4, errors)
    assert errors
    assert "重音音节过少" in errors[0]


def test_en_check_rhyme_group_out_of_range_index(
    monkeypatch: MonkeyPatch,
) -> None:
    """_check_rhyme_group 索引越界应跳过（覆盖 en 115）。"""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["AY1 T"])
    errors: list[str] = []
    en_check_rhyme_group(["word"], [0, 99], "A", errors)
    assert errors == []


def test_en_rhyme_key_no_tails_and_rhyme_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """无重音尾串时 _en_rhyme_key 返回 None（80）且 _check_rhyme_group
    追加'韵脚未落在重音'错误（覆盖 en 118-119）。"""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: [])
    assert _en_rhyme_key("word") is None
    errors: list[str] = []
    en_check_rhyme_group(["word"], [0], "A", errors)
    assert any("韵脚未落在主重音或次重音音节上" in e for e in errors)


def test_en_check_rhyme_group_mismatch(monkeypatch: MonkeyPatch) -> None:
    """组内各行韵尾不一致时应报错（覆盖 en 122-128）。"""

    def _fake_tails(word: str) -> list[str]:
        """mock 的 rhyme_tails：为不同词返回固定韵尾以构造押韵冲突。

        Args:
            word: 待查韵尾的词。

        Returns:
            韵尾列表。
        """
        return ["T1"] if word == "aaa" else ["T2"]

    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", _fake_tails)
    errors: list[str] = []
    en_check_rhyme_group(["aaa", "bbb"], [0, 1], "A", errors)
    assert any("押韵A不匹配" in e for e in errors)


def test_en_sonnet_ab_overlap(monkeypatch: MonkeyPatch) -> None:
    """商籁体同段 A/B 韵脚重叠时应报错（覆盖 en 177, 183-186）。"""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["X1"])
    monkeypatch.setattr(en_module, "_check_stress_count", lambda *a: None)
    poem = [f"line {i} x" for i in range(14)]
    errors = ShakespeareSonnetTemplate().validate_full(poem, [[]] * 14)
    assert any("A/B 韵脚应不同" in e for e in errors)


def test_en_villanelle_ab_overlap(monkeypatch: MonkeyPatch) -> None:
    """维拉内拉诗 A/B 韵脚重叠时应报错（覆盖 en 241）。"""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["AY1 T"])
    monkeypatch.setattr(en_module, "_check_stress_count", lambda *a: None)
    poem = ["the night", "the night"]
    heavy = Syllable(attributes={"stress": "heavy"})
    syllables: list[list[Syllable]] = [[heavy] * 5, [heavy] * 5]
    errors = VillanelleTemplate().validate_full(poem, syllables)
    assert any("A/B韵脚应不同" in e for e in errors)


def test_en_concrete_templates_methods() -> None:
    """实例化全部英语模板并调用各公有方法。"""
    for tmpl in (
        ShakespeareSonnetTemplate(),
        VillanelleTemplate(),
        HeroicCoupletTemplate(),
    ):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None or isinstance(
            tmpl.get_syllable_constraints(), list
        )
        assert isinstance(tmpl.validate_full([], []), list)


def test_fr_last_word_empty() -> None:
    """fr._last_word 对空行应返回空串（覆盖 fr 30）。"""
    assert fr_last_word("   ") == ""


def test_fr_check_rhyme_group_out_of_range_index(
    monkeypatch: MonkeyPatch,
) -> None:
    """fr._check_rhyme_group 索引越界应跳过（覆盖 fr 48）。"""
    monkeypatch.setattr(fr_module._FR, "rhyme_key", lambda w: "x")
    errors: list[str] = []
    fr_check_rhyme_group(["mot"], [0, 99], "A", errors)
    assert errors == []


def test_fr_ballade_invalid_syllable_count() -> None:
    """叙事歌首行音节数非 8/10 时应报错（覆盖 fr 170）。"""
    syl = Syllable(nucleus="a", coda="t")
    syllables: list[list[Syllable]] = [[syl] * 5]
    errors = BalladeTemplate().validate_full([], syllables)
    assert any("叙事歌每行应为8或10音节" in e for e in errors)


def test_fr_concrete_templates_methods() -> None:
    """实例化全部法语模板并调用各公有方法。"""
    for tmpl in (RondeauTemplate(), TrioletTemplate(), BalladeTemplate()):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None
        assert isinstance(tmpl.validate_full([], []), list)


def test_it_canzone_too_many_rhymes() -> None:
    """歌谣韵脚超过 4 个时应报错（覆盖 it 203）。"""
    syllables: list[list[Syllable]] = [
        [Syllable(nucleus=chr(ord("a") + i), coda="x")] for i in range(13)
    ]
    errors = CanzoneTemplate().validate_full(["x"] * 13, syllables)
    assert any("全诗韵脚数量应为4个以内" in e for e in errors)


def test_it_concrete_templates_methods() -> None:
    """实例化全部意大利语模板并调用各公有方法。"""
    for tmpl in (TerzaRimaTemplate(), OttavaRimaTemplate(), CanzoneTemplate()):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None
        dummy: list[list[Syllable]] = [[Syllable()] for _ in range(tmpl.lines)]
        assert isinstance(tmpl.validate_full(["x"] * tmpl.lines, dummy), list)
