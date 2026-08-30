# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""英语/法语音节分析器补充单测（覆盖缺失分支，目标 100% 行覆盖）。

本文件不修改任何既有测试，仅新增针对 `src/prosody/english.py` 与
`src/prosody/french.py` 中未覆盖分支的单元测试：

- 英语：CMUdict 惰性加载体、本地词库回退、64 组合上限、无元音音素串、
  相邻元音跳过、双辅音归并、未知词无元音回退。
- 法语：空词、鼻化后部归并、问号核韵脚、单词语节数、空音节跳过、
  联诵、整行变体。
"""

from unittest import mock

import nltk  # type: ignore[import-untyped]

from src.knowledge import vocabulary
from src.prosody import english as english_module
from src.prosody.english import EnglishAnalyzer
from src.prosody.french import FrenchAnalyzer


def test_load_cmudict_body_executes() -> None:
    """验证 `_load_cmudict` 加载体在本次会话中真实执行（覆盖 63-64, 66-67, 70, 72, 74）。

    直接将 mock 注入 ``nltk.corpus.__dict__``，避免任何对 ``nltk.corpus.cmudict``
    直接注入 ``sys.modules["nltk.corpus"]`` 的 ``cmudict`` 属性（``nltk.corpus``
    作为 LazyModule 代理与 import 实际解析的 ``sys.modules`` 实体并非同一对象，
    必须改动后者才能拦截函数内的 ``from nltk.corpus import cmudict``）；内部强制
    ``nltk.data.find`` 抛 LookupError 以触发 except 下载分支（覆盖 68-69）。
    测试结束后还原全局状态。
    """
    import importlib
    import sys

    importlib.import_module(
        "nltk.corpus"
    )  # 确保 sys.modules 中存在真实模块，避免在干净环境下注入落空

    gl = english_module._load_cmudict.__globals__
    saved_loaded = gl["_cmudict_loaded"]
    saved_cache = gl["_ARPABET_TO_PHONEMES"]
    real_corpus = sys.modules["nltk.corpus"]
    saved_cmu = real_corpus.__dict__.get("cmudict")

    gl["_cmudict_loaded"] = False
    gl["_ARPABET_TO_PHONEMES"] = {}

    fake_dict: dict[str, list[list[str]]] = {"foobar": [["F", "OW1", "B", "AA1", "R"]]}
    mock_cmu = mock.MagicMock()
    mock_cmu.dict.return_value = fake_dict
    try:
        real_corpus.__dict__["cmudict"] = mock_cmu
        with (
            mock.patch.object(nltk.data, "find", side_effect=LookupError),
            mock.patch.object(nltk, "download", return_value=None),
        ):
            english_module._load_cmudict()
        assert gl["_cmudict_loaded"] is True
        assert "foobar" in gl["_ARPABET_TO_PHONEMES"]
    finally:
        if saved_cmu is None:
            real_corpus.__dict__.pop("cmudict", None)
        else:
            real_corpus.__dict__["cmudict"] = saved_cmu
        # 还原全局状态，保证既有用例不受影响
        gl["_cmudict_loaded"] = saved_loaded
        gl["_ARPABET_TO_PHONEMES"] = saved_cache


def test_load_cmudict_inner_guard_return() -> None:
    """验证双检锁内层守卫：外层检查已过、持锁后已加载即返回（覆盖 65）。

    通过替换 `_cmudict_lock` 的 `__enter__`，使其在持锁瞬间将
    `_cmudict_loaded` 置 True，从而命中内层 `if _cmudict_loaded: return`。
    """
    saved_loaded = english_module._cmudict_loaded
    saved_lock = english_module._cmudict_lock

    english_module._cmudict_loaded = False
    fake_lock = mock.MagicMock()

    def _lock_enter(self: object) -> mock.MagicMock:
        """mock 锁的 __enter__：进入时标记 cmudict 已加载并返回锁对象。"""
        english_module._cmudict_loaded = True
        return fake_lock

    fake_lock.__enter__ = _lock_enter
    fake_lock.__exit__ = mock.Mock(return_value=False)
    english_module._cmudict_lock = fake_lock

    english_module._load_cmudict()

    # 内层守卫提前返回，加载体未实际执行
    assert english_module._cmudict_loaded is True
    # 还原全局状态，保证既有用例不受影响
    english_module._cmudict_loaded = saved_loaded
    english_module._cmudict_lock = saved_lock


def test_get_pronunciations_returns_db_prons() -> None:
    """验证本地词库命中时直接返回（覆盖 99）。"""
    analyzer = EnglishAnalyzer()
    prons: list[list[str]] = [["B", "AH1", "R"]]
    with mock.patch.object(vocabulary, "get_en_pron", return_value=prons):
        result = analyzer._get_pronunciations("bar")
    assert result == prons


def test_analyze_line_variants_combo_cap() -> None:
    """验证多音变体组合上限 64（覆盖 193、195 两个 break）。

    每个词返回 4 个发音，4 个词相乘远超 64，触发内层与外层 break。
    """
    analyzer = EnglishAnalyzer()
    four_prons: list[list[str]] = [
        ["B", "AH1"],
        ["K", "AH1"],
        ["D", "AH1"],
        ["F", "AH1"],
    ]
    with mock.patch.object(vocabulary, "get_en_pron", return_value=four_prons):
        combos = analyzer.analyze_line_variants("w1 w2 w3 w4")
    assert len(combos) <= 64
    assert len(combos) == 64


def test_parse_phones_no_vowels() -> None:
    """验证无元音音素串返回空列表（覆盖 217）。"""
    analyzer = EnglishAnalyzer()
    assert analyzer._parse_phones(["B", "T"]) == []


def test_parse_phones_adjacent_vowels_skip() -> None:
    """验证相邻元音（无辅音间隔）跳过空 onset（覆盖 230）。"""
    analyzer = EnglishAnalyzer()
    syls = analyzer._parse_phones(["AE1", "IY0"])
    # 两核相邻，中间无辅音，应切分为两个音节
    assert len(syls) == 2
    assert syls[0].nucleus == "AE"
    assert syls[1].nucleus == "IY"


def test_parse_phones_two_consonant_cluster() -> None:
    """验证两辅音簇首辅音收前音节（覆盖 238-240）。"""
    analyzer = EnglishAnalyzer()
    # B AE1 K T IH0：核间 KT 为双辅音，K 收前、T 归后
    syls = analyzer._parse_phones(["B", "AE1", "K", "T", "IH0"])
    assert len(syls) == 2
    assert syls[0].coda == "K"
    assert syls[1].onset == "T"


def test_fallback_analyze_no_vowels() -> None:
    """验证无元音组未知词回退为单音节（覆盖 269）。"""
    analyzer = EnglishAnalyzer()
    syls = analyzer._fallback_analyze("nth")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_french_syllabify_empty_word() -> None:
    """验证清洗后为空串的词返回问号占位音节（覆盖 174）。"""
    analyzer = FrenchAnalyzer()
    syls = analyzer._syllabify_word("'")
    assert len(syls) == 1
    assert syls[0].nucleus == "?"


def test_french_rhyme_key_nasal_back() -> None:
    """验证鼻化后部元音归并为 'on'（覆盖 216）。"""
    analyzer = FrenchAnalyzer()
    assert analyzer.rhyme_key("bon") == "on"


def test_french_rhyme_key_placeholder_nucleus() -> None:
    """验证问号核词返回空韵脚串（覆盖 233）。"""
    analyzer = FrenchAnalyzer()
    assert analyzer.rhyme_key("'") == ""


def test_french_count_syllables_in_word() -> None:
    """验证单词语节数辅助方法（覆盖 245）。"""
    analyzer = FrenchAnalyzer()
    assert analyzer.count_syllables_in_word("bon") == 1


def test_french_syllabify_line_skips_empty_syls() -> None:
    """验证整行切分时跳过无元音的空词（覆盖 276）。"""
    analyzer = FrenchAnalyzer()
    # "bc" 无元音 -> 空音节列表，应被跳过；"bon" 贡献 1 音节
    syls = analyzer.syllabify_line("bc bon")
    assert len(syls) == 1
    assert syls[0].nucleus == "on"


def test_french_syllabify_line_liaison() -> None:
    """验证跨词联诵：前词尾辅音并入后词首 onset（覆盖 285-286）。"""
    analyzer = FrenchAnalyzer()
    # chat(尾辅音 t) + ami(首元音) -> 联诵，ami 首音节 onset 变为 "t"
    syls = analyzer.syllabify_line("chat ami")
    assert syls[0].coda == ""
    assert syls[1].onset == "t"


def test_french_analyze_line_variants() -> None:
    """验证整行变体仅返回标准切分（覆盖 310）。"""
    analyzer = FrenchAnalyzer()
    variants = analyzer.analyze_line_variants("bon")
    assert len(variants) == 1
    assert len(variants[0]) == 1
