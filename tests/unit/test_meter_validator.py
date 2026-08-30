# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""MeterValidator 单元测试（符号层）。"""

from src.models.syllable import Syllable
from src.prosody.meter_validator import (
    MeterValidator,
    ValidationResult,
    _count_matches,
)

GOOD_POEM = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_count_matches_exact() -> None:
    """验证 count matches exact。"""
    assert _count_matches(5, 5) is True
    assert _count_matches(4, 5) is False


def test_count_matches_interval() -> None:
    """验证 count matches interval。"""
    assert _count_matches(15, (15, 17)) is True
    assert _count_matches(18, (15, 17)) is False


def test_validate_good_poem_passes() -> None:
    """验证 validate good poem passes。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    res = v.validate(GOOD_POEM, tpl)
    assert isinstance(res, ValidationResult)
    assert res.passed is True
    assert res.errors == []


def test_validate_wrong_line_count() -> None:
    """验证 validate wrong line count。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    res = v.validate(GOOD_POEM[:3], tpl)
    assert res.passed is False
    assert any("行数不匹配" in e for e in res.errors)


def test_validate_wrong_syllable_count() -> None:
    """验证 validate wrong syllable count。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    bad = list(GOOD_POEM)
    bad[0] = "床前明月"  # 4 字
    res = v.validate(bad, tpl)
    assert res.passed is False
    assert any("第1行音节数不匹配" in e for e in res.errors)


def test_validate_count_only() -> None:
    """验证 validate count only。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    assert v.validate_count_only(GOOD_POEM, tpl).passed is True
    assert v.validate_count_only(GOOD_POEM[:2], tpl).passed is False


def test_validate_line_good_and_bad() -> None:
    """验证 validate line good and bad。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    assert v.validate_line("窗前明月光", 0, tpl).passed is True
    assert v.validate_line("窗前明月", 0, tpl).passed is False


def test_validate_empty_line_no_crash() -> None:
    """含空行时不应抛 IndexError，应报该行音节数不匹配。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    res = v.validate(["床前明月光", "", "举头望明月", "低头思故乡"], tpl)
    assert res.passed is False
    assert any("第2行" in e for e in res.errors)


def test_validate_empty_line_with_constraints_no_crash() -> None:
    """空行 + 逐位约束时同样不应崩溃，应报告缺行。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
    }
    res = v.validate(["床前明月光", "", "举头望明月", "低头思故乡"], tpl)
    assert res.passed is False


def test_validate_constraints_mismatch() -> None:
    """验证 validate constraints mismatch。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        # 仅第 1 行第 1 音节要求平声
        "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
    }
    # 去 (qù, 仄) 不满足平声约束
    bad = ["去前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]
    res = v.validate(bad, tpl)
    assert res.passed is False
    assert any("第1行第1音节不匹配" in e for e in res.errors)


def test_validate_constraints_pass() -> None:
    """验证 validate constraints pass。"""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
    }
    # 床 (chuáng, 平) 满足
    res = v.validate(GOOD_POEM, tpl)
    assert res.passed is True


def test_validate_english_count_variant() -> None:
    """验证 validate english count variant。"""
    v = MeterValidator()
    tpl = {
        "name": "en-test",
        "language": "en",
        "lines": 1,
        "syllables_per_line": [6],
        "syllable_constraints": None,
    }
    assert v.validate_count_only(["I see the light at night"], tpl).passed is True
    assert v.validate_count_only(["light"], tpl).passed is False


def test_validate_full_tries_all_variants() -> None:
    """组合搜索应尝试每行全部变体，任一组合合律即通过（不再只取主变体）。"""

    class StubTemplate:
        """StubTemplate。"""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """validate full。"""
            first = syllables[0]
            if first and first[0].nucleus == "GOOD":
                return []
            return ["bad"]

    v = MeterValidator()
    good = Syllable(onset="", nucleus="GOOD", coda="", attributes={})
    bad = Syllable(onset="", nucleus="BAD", coda="", attributes={})
    other = Syllable(onset="", nucleus="x", coda="", attributes={})
    all_syl: list[list[list[Syllable]]] = [[[bad], [good]], [[other]]]
    errs = v._validate_full_variants(StubTemplate(), ["a", "b"], all_syl, "zh")
    assert errs == []


def test_validate_full_falls_back_to_best_variant() -> None:
    """若无任何组合合律，应回退到错误数最少的组合（不崩溃）。"""

    class StubTemplate:
        """StubTemplate。"""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """validate full。"""
            return ["err"]

    v = MeterValidator()
    a = Syllable(onset="", nucleus="a", coda="", attributes={})
    all_syl: list[list[list[Syllable]]] = [[[a]], [[a]]]
    errs = v._validate_full_variants(StubTemplate(), ["x", "y"], all_syl, "zh")
    assert errs == ["err"]
