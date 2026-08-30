# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""符号层模板单元测试：覆盖各语言模板 validate_full 的格律规则。

此前模板（zh/en/fr/it/la）的格律校验逻辑缺少直接单元测试，本文件补齐覆盖：
孤平、三平尾、近体诗结构（相对/相粘/平仄脚）、押韵、词牌换韵；
英语商籁体/维拉内拉/英雄双行体的重音押韵与叠句；
法语回旋诗/三韵叠句/叙事歌的叠句与音节统一；
意大利语三行体/八行体/歌谣的第10音节重读、链韵与韵脚约束；
拉丁语哀歌双行体的五步格停顿（caesura）、末6音节音长与 AA 押韵。
"""

from src.models.syllable import Syllable
from src.templates.en import (
    HeroicCoupletTemplate,
    ShakespeareSonnetTemplate,
    VillanelleTemplate,
)
from src.templates.fr import BalladeTemplate, RondeauTemplate, TrioletTemplate
from src.templates.it import CanzoneTemplate, OttavaRimaTemplate, TerzaRimaTemplate
from src.templates.la import (
    DistichonTemplate,
    HendecasyllabusTemplate,
    HexameterTemplate,
)
from src.templates.zh import (
    QijueTemplate,
    QilvTemplate,
    WujueTemplate,
    WulvTemplate,
    XiangjianhuanTemplate,
    _check_guping,
    _check_sanpingwei,
)


# --------------------------------------------------------------------------- #
# 音节构造辅助                                                              #
# --------------------------------------------------------------------------- #
def _zs(nucleus: str, coda: str, tone: str) -> Syllable:
    """构造中文音节（平仄 + 韵腹/韵尾）。

    Args:
        nucleus: 韵腹。
        coda: 韵尾。
        tone: 平仄。

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
        specs: (韵腹, 韵尾, 平仄) 元组列表。

    Returns:
        Syllable 列表。
    """
    return [_zs(n, c, t) for (n, c, t) in specs]


def _es(stress: str = "") -> Syllable:
    """构造英文音节（stress 可为 'heavy'/'light'/''）。

    Args:
        stress: 重音标记。

    Returns:
        构造好的 Syllable 实例。
    """
    return Syllable(
        onset="",
        nucleus="a",
        coda="",
        attributes={"tone": "", "stress": stress, "length": ""},
    )


def _en_syls(n_lines: int, n_syl: int = 10) -> list[list[Syllable]]:
    """构造每行 n_syl 音节、偶数位重的英文音节表（满足重音下限）。

    Args:
        n_lines: 行数。
        n_syl: 每行音节数。

    Returns:
        嵌套的 Syllable 列表。
    """
    return [
        [_es("heavy" if i % 2 == 0 else "") for i in range(n_syl)]
        for _ in range(n_lines)
    ]


def _is(nucleus: str, coda: str = "", stress: str = "") -> Syllable:
    """构造意大利语音节（韵腹/韵尾 + 重音）。

    Args:
        nucleus: 韵腹。
        coda: 韵尾。
        stress: 重音标记。

    Returns:
        构造好的 Syllable 实例。
    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": "", "stress": stress, "length": ""},
    )


def _ls(nucleus: str, coda: str = "", length: str = "") -> Syllable:
    """构造拉丁语音节（韵腹/韵尾 + 长短）。

    Args:
        nucleus: 韵腹。
        coda: 韵尾。
        length: 长短标记。

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
# 中文：孤平 / 三平尾（直接单元）                                          #
# --------------------------------------------------------------------------- #
def test_check_guping_direct() -> None:
    """验证 check guping direct。"""
    ping_foot_only_one = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    assert _check_guping(ping_foot_only_one)

    ze_foot = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
        ]
    )
    assert _check_guping(ze_foot) == []

    ping_foot_two = _zline(
        [
            ("a", "", "平"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    assert _check_guping(ping_foot_two) == []


def test_check_sanpingwei_direct() -> None:
    """验证 check sanpingwei direct。"""
    san = _zline([("a", "", "平"), ("a", "", "平"), ("a", "", "平")])
    assert _check_sanpingwei(san)
    not_san = _zline([("a", "", "平"), ("a", "", "平"), ("a", "", "仄")])
    assert _check_sanpingwei(not_san) == []


# --------------------------------------------------------------------------- #
# 中文：五绝 / 七绝 有效与各项违规                                          #
# --------------------------------------------------------------------------- #
def _valid_wujue_syllables() -> list[list[Syllable]]:
    """五绝有效音节列表。

    Returns:
        4 行 Syllable 列表。
    """
    return [
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "ng", "平"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "ng", "平"),
            ]
        ),
    ]


def _valid_qijue_syllables() -> list[list[Syllable]]:
    """七绝有效音节列表。

    Returns:
        4 行 Syllable 列表。
    """
    return [
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "ng", "平"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "ng", "平"),
            ]
        ),
    ]


def test_wujue_valid() -> None:
    """验证 wujue valid。"""
    assert WujueTemplate().validate_full([""] * 4, _valid_wujue_syllables()) == []


def test_wujue_guping_detected() -> None:
    """验证 wujue guping detected。"""
    syls = _valid_wujue_syllables()
    syls[3] = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("孤平" in e for e in errs)


def test_wujue_sanpingwei_detected() -> None:
    """验证 wujue sanpingwei detected。"""
    syls = _valid_wujue_syllables()
    syls[1] = _zline(
        [
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "ng", "平"),
        ]
    )
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("三平尾" in e for e in errs)


def test_wujue_rhyme_mismatch() -> None:
    """验证 wujue rhyme mismatch。"""
    syls = _valid_wujue_syllables()
    syls[3][-1] = _zs("o", "ng", "平")
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("押韵" in e for e in errs)


def test_qijue_valid() -> None:
    """验证 qijue valid。"""
    assert QijueTemplate().validate_full([""] * 4, _valid_qijue_syllables()) == []


def test_wulv_rhyme_mismatch() -> None:
    """验证 wulv rhyme mismatch。"""
    syls: list[list[Syllable]] = []
    for k in range(8):
        tone = "平" if k % 2 == 1 else "仄"
        coda = "ng" if (k % 2 == 1 and k != 7) else ("ong" if k == 7 else "")
        syls.append([_zs("a", coda, tone) for _ in range(5)])
    errs = WulvTemplate().validate_full([""] * 8, syls)
    assert any("押韵" in e for e in errs)


def test_qilv_sanpingwei_detected() -> None:
    """验证 qilv sanpingwei detected。"""
    syls: list[list[Syllable]] = []
    for k in range(8):
        tone = "平" if k % 2 == 1 else "仄"
        syls.append([_zs("a", "", tone) for _ in range(7)])
    syls[1] = [_zs("a", "", "平") for _ in range(7)]
    errs = QilvTemplate().validate_full([""] * 8, syls)
    assert any("三平尾" in e for e in errs)


# --------------------------------------------------------------------------- #
# 中文：词牌 相见欢（换韵 / 平韵转回）                                    #
# --------------------------------------------------------------------------- #
def _xjh_syllables() -> list[list[Syllable]]:
    """相见词牌有效音节列表。

    Returns:
        7 行 Syllable 列表。
    """

    def mk(n: int, key: str | None) -> list[Syllable]:
        """生成 n 个音节的列表，末尾可替换韵尾。

        Args:
            n: 音节数量。
            key: 韵尾标记（None 则不替换）。

        Returns:
            Syllable 列表。
        """
        out: list[Syllable] = []
        for i in range(n):
            if i == n - 1 and key:
                out.append(_zs(key[0], key[1:], ""))
            else:
                out.append(_zs("a", "", ""))
        return out

    return [
        mk(6, "ang"),
        mk(3, "ang"),
        mk(9, "ang"),
        mk(3, "eng"),
        mk(3, "eng"),
        mk(3, "ang"),
        mk(9, "ang"),
    ]


def test_xiangjianhuan_valid() -> None:
    """验证 xiangjianhuan valid。"""
    assert XiangjianhuanTemplate().validate_full([""] * 7, _xjh_syllables()) == []


def test_xiangjianhuan_lower_ping_not_returned() -> None:
    """验证 xiangjianhuan lower ping not returned。"""
    syls = _xjh_syllables()
    syls[6][-1] = _zs("o", "ng", "")
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("转回" in e or "押韵" in e for e in errs)


# --------------------------------------------------------------------------- #
# 英语：商籁体 / 维拉内拉 / 英雄双行体                                   #
# --------------------------------------------------------------------------- #
def test_sonnet_quatrain_ab_distinct() -> None:
    """验证 sonnet quatrain ab distinct。"""
    # A 组末行(行3)与 B 组末行(行4)同韵 -> 同一联内 A/B 韵脚应不同
    poem = [
        "x light",
        "y night",
        "z light",
        "w night",
        "p day",
        "q time",
        "r fire",
        "s happy",
        "m day",
        "n time",
        "o fire",
        "t happy",
        "u light",
        "v night",
    ]
    syls = _en_syls(14)
    errs = ShakespeareSonnetTemplate().validate_full(poem, syls)
    assert any("A/B" in e for e in errs)


def test_sonnet_rhyme_mismatch() -> None:
    """验证 sonnet rhyme mismatch。"""
    poem = [
        "x light",
        "y love",
        "z cat",
        "w stone",
        "p day",
        "q time",
        "r fire",
        "s happy",
        "m day",
        "n time",
        "o fire",
        "t happy",
        "u light",
        "v night",
    ]
    syls = _en_syls(14)
    errs = ShakespeareSonnetTemplate().validate_full(poem, syls)
    assert any("不匹配" in e for e in errs)


def test_villanelle_refrain_mismatch() -> None:
    """验证 villanelle refrain mismatch。"""
    base = [
        "a light",
        "b love",
        "c night",
        "d stone",
        "e day",
        "f time",
        "g fire",
        "h happy",
        "i night",
        "j stone",
        "k day",
        "l time",
        "m fire",
        "n happy",
        "o night",
        "p stone",
        "q day",
        "r time",
        "s night",
    ]
    poem = list(base)
    poem[5] = "DIFFERENT line"
    poem[11] = "DIFFERENT line"
    poem[17] = "DIFFERENT line"
    syls = _en_syls(19)
    errs = VillanelleTemplate().validate_full(poem, syls)
    assert any("叠句" in e for e in errs)


def test_heroic_couplet_rhyme() -> None:
    """验证 heroic couplet rhyme。"""
    poem = ["the light of night", "a song of stone"]
    syls = _en_syls(2)
    errs = HeroicCoupletTemplate().validate_full(poem, syls)
    assert any("不匹配" in e for e in errs)


# --------------------------------------------------------------------------- #
# 法语：回旋诗 / 三韵叠句 / 叙事歌（叠句 + 音节统一）                  #
# --------------------------------------------------------------------------- #
def test_rondeau_refrain_mismatch() -> None:
    """验证 rondeau refrain mismatch。"""
    poem = [
        "premier vers ici mot",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
    ]
    poem[8] = "dernier mot different"
    poem[14] = "dernier mot different"
    t = RondeauTemplate()
    errs = t.validate_full(poem, [[] for _ in range(15)])
    assert any("叠句" in e for e in errs)


def test_triolet_refrain_mismatch() -> None:
    """验证 triolet refrain mismatch。"""
    poem = [
        "refrain un",
        "refrain deux",
        "trois",
        "quatre",
        "cinq",
        "six",
        "sept",
        "huit",
    ]
    poem[3] = "changed"
    poem[6] = "changed"
    poem[7] = "changed deux"
    errs = TrioletTemplate().validate_full(poem, [[] for _ in range(8)])
    assert any("叠句" in e for e in errs)


def test_ballade_syllable_uniform_mismatch() -> None:
    """验证 ballade syllable uniform mismatch。"""
    poem = ["a" for _ in range(28)]
    syls = [[_is("a") for _ in range(8)] for _ in range(28)]
    syls[10] = [_is("a") for _ in range(9)]
    errs = BalladeTemplate().validate_full(poem, syls)
    assert any("音节数不一致" in e for e in errs)


def test_ballade_refrain_mismatch() -> None:
    """验证 ballade refrain mismatch。"""
    poem = ["a" for _ in range(28)]
    syls = [[_is("a") for _ in range(8)] for _ in range(28)]
    poem[15] = "changed refrain"
    poem[23] = "changed refrain"
    poem[27] = "changed refrain"
    errs = BalladeTemplate().validate_full(poem, syls)
    assert any("叠句" in e for e in errs)


# --------------------------------------------------------------------------- #
# 意大利语：三行体 / 八行体 / 歌谣                                        #
# --------------------------------------------------------------------------- #
def test_terzarima_tenth_stress_missing() -> None:
    """验证 terzarima tenth stress missing。"""
    line = [_is("a") for _ in range(11)]
    syls = [line for _ in range(14)]
    errs = TerzaRimaTemplate().validate_full([""] * 14, syls)
    assert any("第10音节" in e for e in errs)


def test_terzarima_rhyme_mismatch() -> None:
    """验证 terzarima rhyme mismatch。"""

    def mk(key: str) -> list[Syllable]:
        """生成 11 音节行，末尾韵尾为 key。

        Args:
            key: 韵尾标记。

        Returns:
            Syllable 列表。
        """
        out = [_is("a") for _ in range(10)]
        out.append(_is(key))
        return out

    aba = [mk("a"), mk("b"), mk("a")]
    bcb = [mk("b"), mk("c"), mk("b")]
    cdc = [mk("c"), mk("d"), mk("c")]
    ded = [mk("d"), mk("e"), mk("d")]
    ee = [mk("e"), mk("e2"), mk("e")]
    syls = aba + bcb + cdc + ded + ee
    poem = [""] * 14
    errs = TerzaRimaTemplate().validate_full(poem, syls)
    assert any("不匹配" in e for e in errs)


def test_ottava_rima_tenth_stress_ok_rhyme_mismatch() -> None:
    """验证 ottava rima tenth stress ok rhyme mismatch。"""

    def mk(key: str) -> list[Syllable]:
        """生成 11 音节行，第十位重音，末尾韵尾为 key。

        Args:
            key: 韵尾标记。

        Returns:
            Syllable 列表。
        """
        out = [_is("a") for _ in range(10)]
        out[9] = _is("a", "", "heavy")
        out.append(_is(key))
        return out

    lines = [mk("a"), mk("b"), mk("a"), mk("b"), mk("a"), mk("b"), mk("c"), mk("c2")]
    errs = OttavaRimaTemplate().validate_full([""] * 8, lines)
    assert any("不匹配" in e for e in errs)


def test_canzone_constraints() -> None:
    """验证 canzone constraints。"""
    syls: list[list[Syllable]] = []

    def eleven(key: str) -> list[Syllable]:
        """生成 11 音节行，第九位重音，末尾韵尾为 key。

        Args:
            key: 韵尾标记。

        Returns:
            Syllable 列表。
        """
        out = [_is("x") for _ in range(11)]
        out[9] = _is("x", "", "heavy")
        out[10] = _is("y")
        out[-1] = _is(key)
        return out

    def seven(key: str) -> list[Syllable]:
        """生成 7 音节行，末尾韵尾为 key（重音）。

        Args:
            key: 韵尾标记。

        Returns:
            Syllable 列表。
        """
        out = [_is("x") for _ in range(7)]
        out[-1] = _is(key, "", "heavy")
        return out

    for i in range(6):
        syls.append(eleven("a"))
    for i in range(6):
        syls.append(seven("a"))
    syls.append(seven("a"))
    errs = CanzoneTemplate().validate_full([""] * 13, syls)
    assert any("连续同一韵脚" in e or "末三行" in e for e in errs)


# --------------------------------------------------------------------------- #
# 拉丁语：六步格 / 哀歌双行体 / 十一音节诗                              #
# --------------------------------------------------------------------------- #
def test_hexameter_all_short_reports_error() -> None:
    """验证 hexameter all short reports error。"""
    syls = [_ls("a", "", "short") for _ in range(14)]
    errs = HexameterTemplate().validate_full(["x"], [syls])
    assert errs


def test_distichon_caesura_missing() -> None:
    """验证 distichon caesura missing。"""
    hexa = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
    ]
    penta = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
    ]
    penta[-6:] = [_ls("a", "", "short") for _ in range(6)]
    t = DistichonTemplate()
    errs = t.validate_full(["arma virum", "armavirumquecano"], [hexa, penta])
    assert any("caesura" in e for e in errs)


def test_distichon_rhyme_mismatch() -> None:
    """验证 distichon rhyme mismatch。"""
    hexa = [_ls("a", "ng", "long") for _ in range(14)]
    penta = [_ls("a", "ng", "long") for _ in range(12)]
    hexa[-1] = _ls("a", "ng", "long")
    penta[-1] = _ls("o", "ng", "long")
    errs = DistichonTemplate().validate_full(
        ["arma virum", "armavirumquecano"], [hexa, penta]
    )
    assert any("押韵" in e for e in errs)


def test_hendecasyllabus_boundary_missing() -> None:
    """验证 hendecasyllabus boundary missing。"""
    line = [_ls("a", "", "long") for _ in range(11)]
    line[1] = _ls("a", "", "long")
    line[3] = _ls("a", "", "long")
    line[4] = _ls("a", "", "long")
    line[6] = _ls("a", "", "long")
    line[8] = _ls("a", "", "long")
    line[9] = _ls("a", "", "long")
    errs = HendecasyllabusTemplate().validate_full(["aaaaaaaaaaa"], [line])
    assert any("边界" in e for e in errs)


def test_hendecasyllabus_missing_long() -> None:
    """验证 hendecasyllabus missing long。"""
    line = [_ls("a", "", "short") for _ in range(11)]
    errs = HendecasyllabusTemplate().validate_full(["a a a a a a a a a a a"], [line])
    assert any("长音节" in e for e in errs)
