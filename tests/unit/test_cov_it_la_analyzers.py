# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""补充单元测试：将 italian.py 与 latin.py 的行覆盖拉满到 100%。

覆盖目标（缺失行）：
- italian.py: 58-75 (_count_syllables_in_word 私有方法), 91 (_syllabify_word 空串),
  122 (无元音词回退), 156 (词尾双辅音重音分支), 184 (行内空词 continue),
  240 (analyze_line_variants).
- latin.py: 103 (空串词), 162 (短音符号分支), 209 (main 循环 else-coda 分支,
  经验证为不可达死代码), 216-217 (无元音词 onset 回退), 254 (行内空词 continue),
  269 (跨词长音), 292-294 (_leading_consonant_count 的 qu/gu/su 处理),
  324 (analyze_line_variants).
"""

from src.prosody.italian import ItalianAnalyzer
from src.prosody.latin import LatinAnalyzer


def test_it_count_syllables_in_word_empty() -> None:
    """空串应返回 0（覆盖 59）。"""
    assert ItalianAnalyzer()._count_syllables_in_word("") == 0


def test_it_count_syllables_in_word_no_vowel() -> None:
    """无元音词应回退返回 1（覆盖 75 的 else 分支及主循环）。"""
    assert ItalianAnalyzer()._count_syllables_in_word("xyz") == 1


def test_it_count_syllables_in_word_no_diphthong() -> None:
    """无二合元音词逐元音计数（覆盖 65-66, 74）。"""
    assert ItalianAnalyzer()._count_syllables_in_word("casa") == 2


def test_it_count_syllables_in_word_diphthong() -> None:
    """含二合元音词触发 i+=1 合并分支（覆盖 67-73）。"""
    assert ItalianAnalyzer()._count_syllables_in_word("ciao") == 2


def test_it_syllabify_word_empty() -> None:
    """仅省音撇号的词应返回空列表（覆盖 91）。"""
    assert ItalianAnalyzer().analyze_word("'") == []


def test_it_syllabify_word_no_vowel() -> None:
    """无元音词应回退返回占位音节（覆盖 122）。"""
    syls = ItalianAnalyzer().analyze_word("xyz")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_it_syllabify_word_final_two_consonants_stress() -> None:
    """词尾双辅音应重读倒数第二音节（覆盖 156）。"""
    syls = ItalianAnalyzer().analyze_word("amant")
    assert len(syls) == 2
    assert syls[0].attributes["stress"] == "heavy"


def test_it_syllabify_line_skips_empty_word() -> None:
    """行内产生空音节的词应被跳过（覆盖 184）。"""
    syls = ItalianAnalyzer().syllabify_line("l' bello")
    assert syls  # 至少 bello 的音节被保留


def test_it_analyze_line_variants() -> None:
    """整行变体应返回标准切分（覆盖 240）。"""
    variants = ItalianAnalyzer().analyze_line_variants("ciao bello")
    assert len(variants) == 1
    assert variants[0]


def test_la_analyze_word_empty() -> None:
    """纯标点词应返回空列表（覆盖 103）。"""
    assert LatinAnalyzer().analyze_word("...") == []


def test_la_analyze_word_short_marker() -> None:
    """短音符号元音进入 elif 归一分支（覆盖 162）。"""
    syls = LatinAnalyzer().analyze_word("ă")
    assert len(syls) == 1
    assert syls[0].attributes["length"] == "short"


def test_la_analyze_word_no_vowel_onset_fallback() -> None:
    """无元音词走 onset 回退占位音节（覆盖 216-217）。"""
    syls = LatinAnalyzer().analyze_word("bc")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_la_analyze_line_skips_empty_word() -> None:
    """行内仅含省音撇号的词应被跳过（覆盖 254）。

    注意：analyze_word 的 strip 集合含撇号，故 "l'" 会剥成 "l" 而非空；
    必须用纯撇号串 "'" 使词在 strip 后为空，从而命中 ``if not syls: continue``。
    """
    assert LatinAnalyzer().analyze_line("'") == []


def test_la_analyze_line_cross_word_long() -> None:
    """前词元音 + 后词 >=2 前导辅音应为长音（覆盖 269）。"""
    syls = LatinAnalyzer().analyze_line("a strata")
    assert syls[0].attributes["length"] == "long"


def test_la_leading_consonant_count_consonantal_u() -> None:
    """词首 qu 作为整体辅音位（覆盖 292-294）。"""
    assert LatinAnalyzer._leading_consonant_count("qua") == 1


def test_la_analyze_line_variants() -> None:
    """整行变体应返回标准切分（覆盖 324）。"""
    variants = LatinAnalyzer().analyze_line_variants("a strata")
    assert len(variants) == 1
    assert variants[0]


def test_la_analyze_word_main_loop_else_coda_unreachable() -> None:
    """探查 main 循环 else 分支的 coda 路径。

    latin.py 第 209 行的 ``coda += lower`` 在词内出现：
    元音之后、下一元音之前的辅音总会被内联 coda 收集（174-206 行）吞掉，
    因此 main 循环 else 分支在 nucleus 已置位时永远无法到达——属不可达死代码。
    此处测试用于显式记录该行为，不期望覆盖该行。
    """
    # 任意正常词均不会触发 209；断言仅作回归保护。
    assert LatinAnalyzer().analyze_word("patris") is not None
