# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for MeterValidator (symbol layer)."""

from src.models.syllable import Syllable
from src.prosody.meter_validator import (
    MeterValidator,
    ValidationResult,
    _count_matches,
)

GOOD_POEM = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_count_matches_exact() -> None:
    """Verify _count_matches for exact counts."""
    assert _count_matches(5, 5) is True
    assert _count_matches(4, 5) is False


def test_count_matches_interval() -> None:
    """Verify _count_matches for an interval."""
    assert _count_matches(15, (15, 17)) is True
    assert _count_matches(18, (15, 17)) is False


def test_validate_good_poem_passes() -> None:
    """Verify a well-formed poem passes validation."""
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
    """Verify validation fails on a wrong line count."""
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
    assert any("line count mismatch" in e.lower() for e in res.errors)


def test_validate_wrong_syllable_count() -> None:
    """Verify validation fails on a wrong syllable count."""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    bad = list(GOOD_POEM)
    bad[0] = "床前明月"  # 4 characters.
    res = v.validate(bad, tpl)
    assert res.passed is False
    assert any("Line 1 syllable count mismatch" in e for e in res.errors)


def test_validate_count_only() -> None:
    """Verify validate_count_only ignores constraints."""
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
    """Verify validate_line for a good and a bad line."""
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
    """Verify an empty line reports a count mismatch instead of raising IndexError."""
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
    assert any("Line 2" in e for e in res.errors)


def test_validate_empty_line_with_constraints_no_crash() -> None:
    """Verify an empty line with position constraints also reports instead of crashing."""
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
    """Verify validation fails on a constraint mismatch."""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        # Only line 1, syllable 1 requires the level tone.
        "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
    }
    # 望 (wàng, oblique; no level-tone reading) does not satisfy the level-tone constraint.
    bad = ["望前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]
    res = v.validate(bad, tpl)
    assert res.passed is False
    assert any("Line 1 syllable 1 mismatch" in e for e in res.errors)


def test_validate_constraints_pass() -> None:
    """Verify validation passes when constraints are satisfied."""
    v = MeterValidator()
    tpl = {
        "name": "五绝",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
    }
    # 床 (chuáng, level tone) satisfies it.
    res = v.validate(GOOD_POEM, tpl)
    assert res.passed is True


def test_validate_english_count_variant() -> None:
    """Verify the English syllable-count variant."""
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
    """Verify the combined search tries every per-line variant.

    Any metrical combination passes (no longer using only the primary variant).
    """

    class StubTemplate:
        """StubTemplate."""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """Validate full."""
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
    """Verify fallback to the best variant when no combination is metrical."""

    class StubTemplate:
        """StubTemplate."""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """Validate full."""
            return ["err"]

    v = MeterValidator()
    a = Syllable(onset="", nucleus="a", coda="", attributes={})
    all_syl: list[list[list[Syllable]]] = [[[a]], [[a]]]
    errs = v._validate_full_variants(StubTemplate(), ["x", "y"], all_syl, "zh")
    assert errs == ["err"]
