# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Add unit tests that bring syllable_counter, base and meter_validator to 100%."""

from typing import Any
from unittest import mock

from src.models.syllable import Syllable
from src.prosody import syllable_counter as sc_module
from src.prosody.base import SyllableAnalyzer
from src.prosody.meter_validator import MeterValidator, ValidationResult
from src.prosody.syllable_counter import analyze_line


class _BaseStub(SyllableAnalyzer):
    """Base stub without analyze_line_variants (for the line 118 branch)."""

    language = "xx"

    def analyze_word(self, word: str) -> list[Syllable]:
        """Return an empty syllable list.

        Args:
            word: Word to analyze.

        Returns:
            An empty list.

        """
        return []

    def count_syllables(self, text: str) -> int:
        """Return 0.

        Args:
            text: Text to count.

        Returns:
            Always 0.

        """
        return 0


def test_analyze_line_zh_all_empty_variants_returns_empty() -> None:
    """Verify _zh_line returns [] when all Zh variants are empty (line 46)."""

    class _ZhEmptyStub(_BaseStub):
        """analyze_line_variants returns only an empty variant list."""

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return a list containing only an empty variant."""
            return [[]]

    stub = _ZhEmptyStub()
    with mock.patch.dict(sc_module._ANALYZERS, {"zh": stub}):
        assert analyze_line("any", "zh") == []


def test_analyze_line_it_routes_to_syllabify_line() -> None:
    """Verify Italian routes to the _it_line branch (line 59)."""
    syls = analyze_line("poeti e", "it")
    assert isinstance(syls, list)
    assert all(isinstance(s, Syllable) for s in syls)


def test_analyze_line_en_default_branch() -> None:
    """Verify unhandled languages use the per-word default (139-144)."""
    syls = analyze_line("hello world", "en")
    assert isinstance(syls, list)


def test_base_default_tokenize_line() -> None:
    """Verify the default tokenize_line splits on whitespace (base 53)."""

    class _Concrete(SyllableAnalyzer):
        """Minimal subclass implementing only the two abstract methods."""

        language = "concrete"

        def analyze_word(self, word: str) -> list[Syllable]:
            """Return an empty list."""
            return []

        def count_syllables(self, text: str) -> int:
            """Return 0."""
            return 0

    assert _Concrete().tokenize_line("a b  c") == ["a", "b", "c"]


def test_validate_analyzer_without_variants_uses_analyze_line() -> None:
    """Verify an analyzer without analyze_line_variants takes line 118."""
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
    """Verify empty line variants raise the no-syllables error (140-141)."""

    class _EnEmptyStub(_BaseStub):
        """analyze_line_variants returns an empty list."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return an empty variant list."""
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
    assert any("no syllables" in e for e in res.errors)


def test_validate_full_variants_order_and_empty_line() -> None:
    """Cover the En ordering branch (198) and empty-variant line (235)."""

    class _FullStub(_BaseStub):
        """analyze_line_variants returns [] for an empty line else one variant."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return empty for an empty line, else a single-syllable variant."""
            if line == "empty":
                return []
            return [[Syllable(onset="", nucleus="x", coda="", attributes={})]]

    class _FullTemplate:
        """Template stub that always returns errors."""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """Always return a non-empty error list."""
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
    """Cover validate_line's En count branch (lines 327-329)."""

    class _EnStub(_BaseStub):
        """analyze_line_variants returns one non-empty variant."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return a variant of length 1."""
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
    assert any("Syllable count mismatch" in e for e in res.errors)


def test_validate_line_en_constraint_matches_returns() -> None:
    """Verify the En constraint branch returns on a variant match (341-345)."""

    class _EnMatchStub(_BaseStub):
        """analyze_line_variants returns a variant satisfying the constraint."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return a variant with onset=z."""
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
    """Verify the En constraint branch falls back to variants[0] (line 346)."""

    class _EnMismatchStub(_BaseStub):
        """analyze_line_variants returns a variant that misses the constraint."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return a variant with onset=a (the constraint requires z)."""
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
    assert any("Syllable 1" in e for e in res.errors)


def test_describe_constraint_onset_nucleus_coda() -> None:
    """Cover _describe_constraint's onset/nucleus/coda branches (372-376)."""
    desc = MeterValidator._describe_constraint(
        {"onset": "zh", "nucleus": "a", "coda": "ng"}
    )
    assert desc == "onset=zh,nucleus=a,coda=ng"


def test_describe_syllable_with_coda() -> None:
    """Cover _describe_syllable's coda branch (line 398)."""
    desc = MeterValidator._describe_syllable(
        Syllable(onset="z", nucleus="a", coda="ng", attributes={})
    )
    assert "coda=ng" in desc


def test_validate_full_variants_cap_break() -> None:
    """Verify variant combos are capped at MAX_FULL_COMBOS (line 239)."""

    class _ManyVariants(_BaseStub):
        """Each line has 30 identical variants: 3 lines make 27000 > 20000."""

        language = "en"

        def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
            """Return 30 identical variants."""
            return [
                [Syllable(onset="", nucleus="x", coda="", attributes={})]
                for _ in range(30)
            ]

    class _AlwaysErrorTemplate:
        """Template stub whose validate_full always returns errors."""

        def validate_full(
            self, poem: list[str], syllables: list[list[Syllable]]
        ) -> list[str]:
            """Always return a non-empty error list."""
            return ["err"]

    stub = _ManyVariants()
    v = MeterValidator()
    tpl: dict[str, Any] = {
        "language": "en",
        "lines": 3,
        "syllables_per_line": [1, 1, 1],
        "syllable_constraints": None,
    }
    with mock.patch.dict(sc_module._ANALYZERS, {"en": stub}):
        res = v.validate(["a", "b", "c"], tpl, _AlwaysErrorTemplate())
    assert res.passed is False
