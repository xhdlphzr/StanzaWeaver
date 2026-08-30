# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""补充单元测试：将 syllable_counter / base / meter_validator 行覆盖拉满。"""

from typing import Any
from unittest import mock

from src.models.syllable import Syllable
from src.prosody import syllable_counter as sc_module
from src.prosody.base import SyllableAnalyzer
from src.prosody.meter_validator import MeterValidator, ValidationResult
from src.prosody.syllable_counter import analyze_line


class _BaseStub(SyllableAnalyzer):
    """无 analyze_line_variants 的基类桩（用于 118 分支）。"""

    language = "xx"

    def analyze_word(self, word: str) -> list[Syllable]:
        """返回空音节列表。

        Args:
            word: 待分析单词。

        Returns:
            空列表。
        """
        return []

    def count_syllables(self, text: str) -> int:
        """返回 0。

        Args:
            text: 待计数文本。

        Returns:
            固定返回 0。
        """
        return 0


def test_analyze_line_zh_all_empty_variants_returns_empty() -> None:
    """zh 分析器返回的全是空变体时，_zh_line 应回退到返回 []（覆盖 46）。"""

    class _ZhEmptyStub(_BaseStub):
        """analyze_line_variants 只返回空变体列表。"""

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """返回仅含空变体的列表。"""
            return [[]]

    stub = _ZhEmptyStub()
    with mock.patch.dict(sc_module._ANALYZERS, {"zh": stub}):
        assert analyze_line("any", "zh") == []


def test_analyze_line_it_routes_to_syllabify_line() -> None:
    """it 语言应进入 _it_line 分支（覆盖 59）。"""
    syls = analyze_line("poeti e", "it")
    assert isinstance(syls, list)
    assert all(isinstance(s, Syllable) for s in syls)


def test_analyze_line_en_default_branch() -> None:
    """不在 _LINE_HANDLERS 的语言走默认逐词分支（覆盖 139-144）。"""
    syls = analyze_line("hello world", "en")
    assert isinstance(syls, list)


def test_base_default_tokenize_line() -> None:
    """默认 tokenize_line 应按空白切分（覆盖 base 53）。"""

    class _Concrete(SyllableAnalyzer):
        """仅实现两个抽象方法的极简子类。"""

        language = "concrete"

        def analyze_word(self, word: str) -> list[Syllable]:
            """返回空列表。"""
            return []

        def count_syllables(self, text: str) -> int:
            """返回 0。"""
            return 0

    assert _Concrete().tokenize_line("a b  c") == ["a", "b", "c"]


def test_validate_analyzer_without_variants_uses_analyze_line() -> None:
    """无 analyze_line_variants 的分析器走 118 分支。"""
    stub = _BaseStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "xx",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": None,
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"xx": stub}):
        res = v.validate(["anything"], tpl)
    assert isinstance(res, ValidationResult)
    assert res.passed is False


def test_validate_constraints_empty_variants_reports_error() -> None:
    """某行变体为空时，逐位约束分支应报“无音节”（覆盖 140-141）。"""

    class _EnEmptyStub(_BaseStub):
        """analyze_line_variants 返回空列表。"""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """返回空变体列表。"""
            return []

    stub = _EnEmptyStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": [[{"onset": "z"}]],
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate(["x"], tpl)
    assert any("无音节" in e for e in res.errors)


def test_validate_full_variants_order_and_empty_line() -> None:
    """en 排序分支（198）与空变体行分支（235）同测。"""

    class _FullStub(_BaseStub):
        """analyze_line_variants 对空行返回 []，其余返回单变体。"""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """空行返回空；正常行返回单音节变体。"""
            if line == "empty":
                return []
            return [[Syllable(onset="", nucleus="x", coda="", attributes={})]]

    class _FullTemplate:
        """只返回错误的模板桩。"""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """始终返回非空错误列表。"""
            return ["err"]

    stub = _FullStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 2,
        "syllables_per_line": [1, 1],
        "syllable_constraints": None,
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate(["good", "empty"], tpl, template_obj=_FullTemplate())
    assert isinstance(res, ValidationResult)


def test_validate_line_en_count_branch() -> None:
    """validate_line 的 en 计数分支（327-329）。"""

    class _EnStub(_BaseStub):
        """analyze_line_variants 返回非空单变体。"""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """返回长度 1 的变体。"""
            return [[Syllable(onset="", nucleus="a", coda="", attributes={})]]

    stub = _EnStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 1,
        "syllables_per_line": [99],
        "syllable_constraints": None,
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate_line("text", 0, tpl)
    assert any("音节数不匹配" in e for e in res.errors)


def test_validate_line_en_constraint_matches_returns() -> None:
    """validate_line 的 en 约束分支：变体匹配时直接返回（341-345）。"""

    class _EnMatchStub(_BaseStub):
        """analyze_line_variants 返回满足约束的变体。"""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """返回 onset=z 的变体。"""
            return [[Syllable(onset="z", nucleus="", coda="", attributes={})]]

    stub = _EnMatchStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 1,
        "syllables_per_line": [1],
        "syllable_constraints": [[{"onset": "z"}]],
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate_line("text", 0, tpl)
    assert res.passed is True


def test_validate_line_en_constraint_mismatch_reports() -> None:
    """validate_line 的 en 约束分支：无匹配时取 variants[0]（346）。"""

    class _EnMismatchStub(_BaseStub):
        """analyze_line_variants 返回不满足约束的变体。"""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """返回 onset=a 的变体（约束要求 z）。"""
            return [[Syllable(onset="a", nucleus="", coda="", attributes={})]]

    stub = _EnMismatchStub()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 1,
        "syllables_per_line": [1],
        "syllable_constraints": [[{"onset": "z"}]],
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate_line("text", 0, tpl)
    assert any("第1音节" in e for e in res.errors)


def test_describe_constraint_onset_nucleus_coda() -> None:
    """_describe_constraint 的 onset/nucleus/coda 分支（372/374/376）。"""
    desc = MeterValidator._describe_constraint(
        {"onset": "zh", "nucleus": "a", "coda": "ng"}
    )
    assert desc == "声母=zh,韵母=a,韵尾=ng"


def test_describe_syllable_with_coda() -> None:
    """_describe_syllable 的 coda 分支（398）。"""
    desc = MeterValidator._describe_syllable(
        Syllable(onset="z", nucleus="a", coda="ng", attributes={})
    )
    assert "韵尾=ng" in desc
