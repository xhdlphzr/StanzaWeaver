# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""意大利语音节分析器单元测试（符号层）。"""

from src.models.syllable import Syllable
from src.prosody.italian import ItalianAnalyzer
from src.templates.it import CanzoneTemplate


def test_count_amor() -> None:
    a = ItalianAnalyzer()
    # a-mor: 2 音节，末音节重读（辅音收尾）
    assert a.count_syllables("amor") == 2
    syls = a.analyze_word("amor")
    assert syls[-1].attributes["stress"] == "heavy"


def test_count_citta() -> None:
    a = ItalianAnalyzer()
    # ci-ttà: 2 音节，末音节重读（词尾重音元音）
    assert a.count_syllables("città") == 2


def test_no_sinalefe_when_prev_coda() -> None:
    a = ItalianAnalyzer()
    # amor 末音节韵尾 r 非空 -> 不与 "e" 并读
    assert a.count_syllables("amor e") == 3


def test_sinalefe_merges_cross_word_vowels() -> None:
    a = ItalianAnalyzer()
    # poeti 末元音 i 与 e 并读为一个音节: 3 而非 4
    assert a.count_syllables("poeti e") == 3


def test_sinalefe_hiatus_no_merge() -> None:
    a = ItalianAnalyzer()
    # virtù 末元音 ù 重读 -> 与 eterna 首元音 e 形成元音分裂，不合并
    assert a.count_syllables("virtù eterna") == 5


def test_sinalefe_unstressed_merges() -> None:
    a = ItalianAnalyzer()
    # la 非重读、aria 首元音非重读 -> 合并
    assert a.count_syllables("la aria") == 3


def test_zio_hiatus_two_syllables() -> None:
    a = ItalianAnalyzer()
    # zì-o: 重读 ì 与其后 o 为元音分裂，计 2 音节
    assert a.count_syllables("zìo") == 2
    syls = a.analyze_word("zìo")
    assert len(syls) == 2
    assert syls[0].attributes["stress"] == "heavy"


def _mk_line(n: int, stress_idx: int, tail: str) -> list[Syllable]:
    """构造一行指定音节数、重音位置与韵脚的音节列表。"""
    syls: list[Syllable] = []
    for i in range(n):
        attrs = {
            "tone": "",
            "stress": "heavy" if i == stress_idx else "",
            "length": "",
        }
        syls.append(
            Syllable(
                nucleus=tail if i == n - 1 else "a",
                coda="",
                attributes=attrs,
            )
        )
    return syls


def _mk_canzone() -> list[list[Syllable]]:
    """构造一首全部合律的歌谣（奇数 11 音节第10重读，偶数/末行 7 音节末重读）。"""
    lines: list[list[Syllable]] = []
    for idx in range(13):
        if idx % 2 == 0:
            # 奇数行：11 音节，第 10 音节（0-based 9）重读
            lines.append(_mk_line(11, 9, "a"))
        else:
            # 偶数行：7 音节，末音节（0-based 6）重读
            lines.append(_mk_line(7, 6, "b"))
    # 第 13 行（0-based 12）另用韵脚 c，确保末三行各异
    lines[12] = _mk_line(7, 6, "c")
    return lines


def _validate_canzone(lines: list[list[Syllable]]) -> list[str]:
    poem = ["x"] * 13
    return CanzoneTemplate().validate_full(poem, lines)


def test_canzone_valid_stress() -> None:
    # 完全合律的歌谣不应产生重音类错误
    assert _validate_canzone(_mk_canzone()) == []


def test_canzone_odd_line_stress_on_11_fails() -> None:
    lines = _mk_canzone()
    # 第 1 行（0-based 0）改为第 11 音节重读、第 10 不重读
    lines[0] = _mk_line(11, 10, "a")
    errs = _validate_canzone(lines)
    assert any("第1行第10音节" in e for e in errs)
    assert any("第1行第11音节" in e for e in errs)


def test_canzone_odd_line_missing_tenth_fails() -> None:
    lines = _mk_canzone()
    # 第 1 行（0-based 0）重音落在第 6 音节，第 10 音节未重读
    lines[0] = _mk_line(11, 5, "a")
    errs = _validate_canzone(lines)
    assert any("第1行第10音节" in e for e in errs)


def test_canzone_even_line_final_stressed() -> None:
    lines = _mk_canzone()
    # 偶数行（第 2 行，0-based 1）末音节已重读 -> 无该项错误
    errs = _validate_canzone(lines)
    assert not any("第2行末音节" in e for e in errs)
    # 改为末音节非重读 -> 应报错
    lines[1] = _mk_line(7, 3, "b")
    errs = _validate_canzone(lines)
    assert any("第2行末音节" in e for e in errs)
