# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""补充中文(zh)/拉丁(la)模板单测，覆盖此前缺失的分支行。

本文件只新增单元测试，不修改既有测试，也不修改任何源码。目标为把
``src/templates/zh.py`` 与 ``src/templates/la.py`` 的行覆盖率推到 100%
（个别确属不可达的死代码分支在文件末尾说明）。
"""

from typing import Any

from src.models.syllable import Syllable
from src.templates import _make_syl
from src.templates.la import (
    DistichonTemplate,
    HendecasyllabusTemplate,
    _validate_hex,
)
from src.templates.zh import (
    XiangjianhuanTemplate,
    _check_alternation,
    _check_guping,
    _check_jinti_rhyme,
    _check_jinti_structure,
    _check_lv_alternation,
    _check_rhyme,
    _rhyme_key,
)


# --------------------------------------------------------------------------- #
# 中文音节构造辅助                                                            #
# --------------------------------------------------------------------------- #
def _zs(nucleus: str, coda: str, tone: str) -> Syllable:
    """构造中文音节（韵腹/韵尾 + 平仄）。

    Args:
        nucleus: 韵腹。
        coda: 韵尾。
        tone: 平仄标签（"平"/"仄"/""）。

    Returns:
        构造好的 Syllable 实例。
    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": tone, "stress": "", "length": ""},
    )


def _zline(specs: list[tuple[str, str, str]]) -> list[Syllable]:
    """由 (韵腹, 韵尾, 平仄) 列表构造一行音节。

    Args:
        specs: 逐位 (nucleus, coda, tone) 三元组序列。

    Returns:
        该行音节列表。
    """
    return [_zs(n, c, t) for (n, c, t) in specs]


def _ls(nucleus: str, coda: str, length: str) -> Syllable:
    """构造拉丁语音节（韵腹/韵尾 + 长短）。

    Args:
        nucleus: 韵腹。
        coda: 韵尾。
        length: 长短标签（"long"/"short"/""）。

    Returns:
        构造好的 Syllable 实例。
    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": "", "stress": "", "length": length},
    )


# --------------------------------------------------------------------------- #
# zh.py: _make_syl / _check_guping / _check_alternation / _rhyme_key          #
# --------------------------------------------------------------------------- #
def test_zh_make_syl_non_dict_attrs() -> None:
    """_make_syl 接受非 dict 的 attributes 时回落为空 dict（覆盖第 29 行）。"""
    result = _make_syl(attributes="not-a-dict")
    assert result["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_zh_check_guping_empty() -> None:
    """空行直接返回，不报错（覆盖第 88 行）。"""
    assert _check_guping([]) == []


def test_zh_check_alternation_mismatch() -> None:
    """偶数位平仄与期望不符时报错（覆盖 107-117 行）。"""
    syls = [
        _zs("a", "", "仄"),
        _zs("a", "", "平"),
        _zs("a", "", "仄"),
    ]
    errs = _check_alternation(syls, ["仄", "仄", "仄"])
    assert any("二四六分明" in e for e in errs)


def test_zh_rhyme_key_branches() -> None:
    """舌尖音 + i 归入「支」部；普通韵母查通韵表（覆盖 186/188 行）。"""
    assert _rhyme_key(Syllable(onset="zh", nucleus="i", coda="")) == "支"
    assert _rhyme_key(Syllable(onset="", nucleus="a", coda="")) == "麻"


def test_zh_check_rhyme_too_few_keys() -> None:
    """参与押韵行不足两行时直接返回（覆盖 214 行）。"""
    syls = [[_zs("a", "ng", "平")]]
    assert _check_rhyme(syls, [0]) == []


def test_zh_check_jinti_rhyme_ze_foot_and_few_keys() -> None:
    """偶数行尾字非平声报错；有效韵脚不足两行时返回（覆盖 247/255 行）。"""
    syls = [
        [_zs("a", "", "仄")],
        [_zs("a", "", "仄")],
    ]
    errs = _check_jinti_rhyme(syls, [1], "押韵")
    assert any("应为平声字" in e for e in errs)
    # 仅有仄脚、不足两韵脚时仍会因仄脚报错，随后提前返回（覆盖 255 行）
    errs2 = _check_jinti_rhyme([[_zs("a", "", "仄")]], [0])
    assert any("应为平声字" in e for e in errs2)


def test_zh_jinti_structure_short_and_feet() -> None:
    """行数不足直接返回；出句平脚、对句仄脚报错（覆盖 282/307/312 行）。"""
    assert _check_jinti_structure([[_zs("a", "", "仄")]]) == []
    syls = [
        _zline([("a", "", "仄")] * 5),
        _zline([("a", "", "仄")] * 5),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
            ]
        ),
        _zline([("a", "", "仄")] * 5),
        _zline([("a", "", "仄")] * 5),
    ]
    errs = _check_jinti_structure(syls)
    assert any("出句" in e for e in errs)
    assert any("对句" in e for e in errs)


def test_zh_lv_alternation_helper() -> None:
    """律诗二四六分明辅助检查（覆盖 356-368 行）。"""
    syls = [
        _zs("a", "", "仄"),
        _zs("a", "", "仄"),
        _zs("a", "", "平"),
        _zs("a", "", "仄"),
        _zs("a", "", "仄"),
    ]
    constraints: list[list[dict[str, Any]]] = [
        [
            _make_syl(),
            _make_syl(attributes={"tone": "平"}),
            _make_syl(),
            _make_syl(attributes={"tone": "仄"}),
            _make_syl(),
        ]
    ]
    errs = _check_lv_alternation(syls, 0, constraints)
    assert isinstance(errs, list)
    assert any("二四六分明" in e for e in errs)


# --------------------------------------------------------------------------- #
# zh.py: 相见欢 validate_full（521/537/538/544/548）                          #
# --------------------------------------------------------------------------- #
def _xjh_mk(n: int, key: str | None, force_ping3: bool = False) -> list[Syllable]:
    """构造相见欢某一行音节。

    Args:
        n: 该行音节数。
        key: 末音节韵腹+韵尾（None 表示自由位）。
        force_ping3: 末三字强制为平声（用于触发三平尾提示）。

    Returns:
        该行音节列表。
    """
    out: list[Syllable] = []
    for i in range(n):
        if force_ping3 and i >= n - 3:
            out.append(_zs("a", "ng", "平"))
        elif i == n - 1 and key:
            out.append(_zs(key[0], key[1:], ""))
        else:
            out.append(_zs("a", "", ""))
    return out


def test_xjh_last3_ping_and_huan_yun() -> None:
    """下阕末句三平尾提示；平韵须转回上阕；仄韵须换韵（覆盖 521/537/544/548）。"""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(9, None, force_ping3=True),
        _xjh_mk(3, "ang"),
        _xjh_mk(3, "eng"),
        _xjh_mk(3, "eng"),
        _xjh_mk(9, "ang"),
    ]
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("末三字全平" in e for e in errs)
    assert any("转回" in e for e in errs)
    assert any("换韵" in e for e in errs)


def test_xjh_empty_line_tail() -> None:
    """某行音节为空时 tail 返回空串（覆盖 538 行）。"""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(9, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(3, "eng"),
        [],
        _xjh_mk(9, "ang"),
    ]
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("换韵" in e for e in errs)


# --------------------------------------------------------------------------- #
# la.py: _make_syl / _validate_hex                                            #
# --------------------------------------------------------------------------- #
def test_make_syl_non_dict_attrs() -> None:
    """_make_syl 接受非 dict 的 attributes 时回落为空 dict（覆盖第 32 行）。"""
    result = _make_syl(attributes="nondict")
    assert result["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_la_validate_hex_too_few() -> None:
    """音节数不足 13 时报错并返回（覆盖 64-65 行）。"""
    errs = _validate_hex([_ls("a", "", "short") for _ in range(5)])
    assert any("音节数不足" in e for e in errs)


def test_la_validate_hex_first_short_and_second_short() -> None:
    """首音步首音节非长、第二音步第二音节非长均报错（覆盖 99/109 行）。"""
    syls = [
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
    ]
    errs = _validate_hex(syls)
    assert any("应以长音节开头" in e for e in errs)
    assert any("扬扬格应两个长音节" in e for e in errs)


def test_la_validate_hex_full_scan_valid() -> None:
    """完整 6 音步扫描进入校验循环，前四音步含扬抑抑格（覆盖 103-106 行）。"""
    syls = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
    ]
    errs = _validate_hex(syls)
    assert errs == []


def test_la_validate_hex_sixth_foot_first_short() -> None:
    """第六音步为两音节但首音节非长时报错（覆盖 124-125 行）。"""
    syls: list[Syllable] = []
    for _ in range(4):
        syls.append(_ls("a", "", "long"))
        syls.append(_ls("a", "", "long"))
    syls.append(_ls("a", "", "long"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "long"))
    errs = _validate_hex(syls)
    assert any("第6音步应以长音节开头" in e for e in errs)


# --------------------------------------------------------------------------- #
# la.py: caesura / Distichon / Hendecasyllabus                                #
# --------------------------------------------------------------------------- #
def test_la_pentameter_caesura_total_small() -> None:
    """总音节不足 6 时直接判定无停顿（覆盖 189 行）。"""
    assert DistichonTemplate()._has_pentameter_caesura("arma", 3) is False


def test_la_pentameter_caesura_punct_only() -> None:
    """词界扫描遇到纯标点词时跳过（覆盖 195 行）。"""
    assert DistichonTemplate()._has_pentameter_caesura("...", 6) is False


def test_la_distichon_few_lines() -> None:
    """不足两行时直接返回（覆盖 210 行）。"""
    assert DistichonTemplate().validate_full(["x"], []) == []


def test_la_distichon_pentameter_too_short() -> None:
    """第二行（五步格）音节不足 6 时报不足（覆盖 228-229 行）。"""
    line0 = [_ls("a", "", "long") for _ in range(13)]
    line1 = [_ls("a", "", "long") for _ in range(4)]
    errs = DistichonTemplate().validate_full(["h", "h"], [line0, line1])
    assert any("第2行音节数不足" in e for e in errs)


def test_la_hendeca_empty() -> None:
    """无音节时直接返回（覆盖 276 行）。"""
    assert HendecasyllabusTemplate().validate_full([], []) == []


def test_la_hendeca_too_few() -> None:
    """音节数不足 11 时报错（覆盖 279 行）。"""
    line = [_ls("a", "", "long") for _ in range(5)]
    errs = HendecasyllabusTemplate().validate_full(["x"], [line])
    assert any("音节数不足" in e for e in errs)


def test_la_hendeca_boundary_punct() -> None:
    """词界扫描遇到纯标点词时跳过（仍缺边界）（覆盖 300 行）。"""
    line = [_ls("a", "", "long") for _ in range(11)]
    errs = HendecasyllabusTemplate().validate_full(["..."], [line])
    assert any("边界" in e for e in errs)


# --------------------------------------------------------------------------- #
# 不可达死代码说明                                                            #
# --------------------------------------------------------------------------- #
# 下列缺失行经分析为确属不可达的死代码（即便使用 mock 也无法触发）：
#   * zh.py 217、258：``_rhyme_key`` 永远返回非空串（``raw or "?"``），
#     故 ``base_rhyme`` 不可能为假，对应 ``return errors`` 分支无法进入。
#   * la.py 70：``_validate_hex`` 进入循环前已保证 n>=13，而前 4 音步每步
#     至少消耗 2 音节，i 永远 < n，``break`` 无法到达。
#   * la.py 107：前 4 音步的 3 音节音步仅由扬抑抑扫描（要求 syls[i+1]、
#     syls[i+2] 均为 "short"）创建，与校验时读取的 foot[1]、foot[2] 为同一
#     对象，故该错误条件恒为假。
#   * la.py 114：进入音步校验循环（行 94+）的前提是``len(feet) >= 6``；而第 5
#     音步要出现则必须是 3 音节扬抑抑格（否则无法再凑出第 6 音步，导致
#     ``len(feet) < 6`` 在行 90-92 提前返回），故第 5 音步``len != 3`` 的分支
#     永远无法到达。
#   * la.py 198、303：``analyze_word`` 对任意非空单词必返回 >=1 音节，而调用
#     方在传入前已跳过空 ``w_clean``，故 ``n == 0`` 分支无法进入。
