# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""MeterValidator 单元测试（符号层）。"""

from src.prosody.meter_validator import (
    MeterValidator,
    ValidationResult,
    _count_matches,
)

GOOD_POEM = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_count_matches_exact() -> None:
    assert _count_matches(5, 5) is True
    assert _count_matches(4, 5) is False


def test_count_matches_interval() -> None:
    assert _count_matches(15, (15, 17)) is True
    assert _count_matches(18, (15, 17)) is False


def test_validate_good_poem_passes() -> None:
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


def test_validate_constraints_mismatch() -> None:
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
