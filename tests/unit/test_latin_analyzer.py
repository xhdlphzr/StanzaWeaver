# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""拉丁语音节分析器单元测试（符号层）。"""

from src.models.syllable import Syllable
from src.prosody.latin import LatinAnalyzer
from src.templates.la import DistichonTemplate, HendecasyllabusTemplate


def _syls(lengths: list[str]) -> list[Syllable]:
    """按给定长短构造音节列表。"""
    return [Syllable(nucleus="a", attributes={"length": l}) for l in lengths]


def test_count_syllables_amor() -> None:
    a = LatinAnalyzer()
    assert a.count_syllables("amor") == 2


def test_mutua_cum_liquida_merges() -> None:
    a = LatinAnalyzer()
    # patris: p+t+r 构成 muta cum liquida，仅算一个辅音位 -> 全作 "a" 的 onset
    syls = a.analyze_word("patris")
    assert len(syls) == 2
    assert syls[0].onset == "ptr"
    assert syls[0].nucleus == "a"


def test_diphthong_is_long() -> None:
    a = LatinAnalyzer()
    # au 为双元音 -> 长音
    syls = a.analyze_word("aurum")
    assert syls[0].nucleus == "au"
    assert syls[0].attributes["length"] == "long"


def test_consonantal_u() -> None:
    a = LatinAnalyzer()
    # qu 中 u 为辅音性，不构成独立音节
    syls = a.analyze_word("aqua")
    assert len(syls) == 2
    assert syls[0].onset == "qu"


def test_leading_consonant_count() -> None:
    a = LatinAnalyzer()
    # muta cum liquida 仅算 1
    assert a._leading_consonant_count("tr") == 1
    # x 计为 2 个辅音位
    assert a._leading_consonant_count("tx") == 3
    # 普通塞音为 1
    assert a._leading_consonant_count("patris") == 1


def test_analyze_line_cross_word_length() -> None:
    a = LatinAnalyzer()
    # arma(2) + virum(2) = 4 音节
    assert len(a.analyze_line("arma virum")) == 4


def test_fl_fr_not_mutacumliquida() -> None:
    a = LatinAnalyzer()
    # 'f' 是擦音而非塞音，故 "fr" 不算 muta cum liquida；
    # 前接元音 "a" 后跟 f+r 两个辅音 -> 占位成位 -> 长音。
    syls = a.analyze_word("afrī")
    assert syls[0].attributes["length"] == "long"


def test_fuimus_three_syllables() -> None:
    a = LatinAnalyzer()
    # "ui" 不是双元音，须拆成 u+i -> fu-i-mus 共 3 音节。
    assert len(a.analyze_word("fuimus")) == 3


def test_macron_diphthong_ae() -> None:
    a = LatinAnalyzer()
    # 带长音符号的 "āe" 仍应识别为双元音 ae 且为长音。
    syls = a.analyze_word("āe")
    assert len(syls) == 1
    assert syls[0].nucleus == "ae"
    assert syls[0].attributes["length"] == "long"


def test_elision_reduces_syllables() -> None:
    a = LatinAnalyzer()
    # vita 以元音 a 结尾，est 以元音 e 开头 -> 省音，末音节被吞。
    # 正常 vi-ta-est = 3，省音后 vi-test = 2。
    assert len(a.analyze_line("vita est")) == 2


def test_hendecasyllabic_syllable5_long() -> None:
    t = HendecasyllabusTemplate()
    # 约束表第 5 音节（index 4）必须为长。
    cons = t.get_syllable_constraints()
    assert cons[0][4]["attributes"]["length"] == "long"
    # 构造 11 音节，第 5 音节为短 -> validate_full 应报第 5 音节须长。
    lengths = [
        "long",
        "short",
        "long",
        "short",
        "short",
        "long",
        "short",
        "long",
        "short",
        "long",
        "short",
    ]
    errs = t.validate_full(["parulapara"], [_syls(lengths)])
    assert any("第5音节" in e for e in errs)


def test_distichon_pentameter_caesura() -> None:
    t = DistichonTemplate()
    # 末 6 音节须为 long short short long short short。
    tail = ["long", "short", "short", "long", "short", "short"]
    pent = _syls(["long", "short", "short", "long", "short"] + tail)  # 11 音节

    # 良好：前半 5 音节后（倒数第 6 前）有词界。
    good_poem = ["", "parulapara parulaparapa"]
    errs_good = t.validate_full(good_poem, [[], pent])
    assert not any("caesura" in e for e in errs_good)

    # 不良：整行仅一个 11 音节词，前半与后半之间无词界。
    bad_poem = ["", "aaaaaaaaaaa"]
    errs_bad = t.validate_full(bad_poem, [[], pent])
    assert any("caesura" in e for e in errs_bad)
