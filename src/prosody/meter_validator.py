# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Overall meter validator (MeterValidator).

Runs a layered validation over a whole poem:
1. Line-count match;
2. Syllable count per line (passes when any division variant matches);
3. Per-position syllable constraints (tone/stress/length), passing when any
   division variant matches; multiple constraint tables
   (syllable_constraint_alternatives) are in an "OR" relation: satisfying any
   one table suffices;
4. Template-specific full rules (validate_full: rhyme, three-level tail,
   solitary level, etc.).

Layer 4 no longer uses only the primary variant; it feeds every pronunciation
/ division variant of each line into the review, doing a combinatorial search
over line variants and accepting the poem when any combination passes all
rules.
"""

import itertools
from dataclasses import dataclass, field
from typing import Any

# Maximum number of combinations when searching line variants; excess is
# truncated (avoids combinatorial explosion from Italian sinalefe / English
# multiple divisions), returning the combination with the fewest errors after
# truncation.
MAX_FULL_COMBOS = 20000

from ..models.syllable import Syllable
from ..templates import format_count
from .syllable_counter import get_analyzer

SyllableCount = int | tuple[int, int]
Constraint = dict[str, Any]
ConstraintLine = list[Constraint]
ConstraintTable = list[ConstraintLine]
TemplateDict = dict[str, Any]
VariantList = list[list[Syllable]]


def _count_matches(actual: int, expected: SyllableCount) -> bool:
    """Check whether the actual syllable count matches the expectation.

    The expectation may be a fixed value or a range.

    Args:
        actual: Actual syllable count.
        expected: int fixed value or (min, max) range.

    Returns:
        True when it matches.

    """
    if isinstance(expected, (tuple, list)) and len(expected) == 2:
        return expected[0] <= actual <= expected[1]
    return actual == expected


@dataclass
class ValidationResult:
    """Result of one meter validation.

    Attributes:
        passed: Whether everything passed.
        errors: List of error messages (human-readable, used for LLM
            correction prompts and frontend display).

    """

    passed: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        """Append an error and mark the result as failed.

        Args:
            msg: Error description.

        """
        self.passed = False
        self.errors.append(msg)


class MeterValidator:
    """Multi-language overall meter validator (symbolic layer, zero AI cost)."""

    def validate(
        self,
        poem: list[str],
        template: TemplateDict,
        template_obj: object = None,
    ) -> ValidationResult:
        """Validate a whole poem.

        Args:
            poem: List of poem lines.
            template: Template dictionary (output of to_dict()).
            template_obj: Template object (full rule checks run when it has
                validate_full).

        Returns:
            Validation result (with all errors).

        """
        language = str(template.get("language", "zh"))
        lines_expected = int(template.get("lines", len(poem)))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )
        constraints_raw = template.get("syllable_constraints", [])
        alternatives = self._constraint_alternatives(template)
        constraints: ConstraintTable = list(constraints_raw) if constraints_raw else []

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"Line count mismatch: expected {lines_expected} lines, "
                f"actual {len(poem)} lines"
            )

        all_syllables: list[VariantList] = []
        for i in range(len(poem)):
            analyzer = get_analyzer(language)
            all_syllables.append(analyzer.analyze_line_variants(poem[i]))

        for i in range(min(len(poem), len(syllables_expected))):
            expected_count = syllables_expected[i]
            variants = all_syllables[i]
            if not variants:
                result.add_error(
                    f"Line {i + 1} syllable count mismatch: "
                    f"expected {format_count(expected_count)}, actual 0"
                )
                continue
            if not any(_count_matches(len(v), expected_count) for v in variants):
                actual_count = len(variants[0])
                result.add_error(
                    f"Line {i + 1} syllable count mismatch: "
                    f"expected {format_count(expected_count)}, "
                    f"actual {actual_count}"
                )

        if alternatives:
            for err in self._best_alternative_errors(all_syllables, alternatives):
                result.add_error(err)
        elif constraints:
            for err in self._constraint_errors(all_syllables, constraints):
                result.add_error(err)

        if template_obj is not None and hasattr(template_obj, "validate_full"):
            full_errors = self._validate_full_variants(
                template_obj, poem, all_syllables, language
            )
            for err in full_errors:
                result.add_error(err)

        return result

    @staticmethod
    def _constraint_alternatives(template: TemplateDict) -> list[ConstraintTable]:
        """Read the template's multiple per-position constraint tables (OR).

        Args:
            template: Template dictionary.

        Returns:
            List of constraint tables; empty when no multiple constraints are
            configured.

        """
        raw = template.get("syllable_constraint_alternatives")
        if not raw:
            return []
        return [list(table or []) for table in raw]

    def _best_alternative_errors(
        self,
        all_syllables: list[VariantList],
        alternatives: list[ConstraintTable],
    ) -> list[str]:
        """Check multiple per-position tables: pass if any matches.

        Otherwise return the errors of the table with the fewest errors.

        Args:
            all_syllables: One variant list per line.
            alternatives: Multiple constraint tables.

        Returns:
            Error list; empty when a satisfying table exists.

        """
        best: list[str] | None = None
        for table in alternatives:
            errors = self._constraint_errors(all_syllables, table)
            if not errors:
                return []
            if best is None or len(errors) < len(best):
                best = errors
        return best or []

    @staticmethod
    def _constraint_errors(
        all_syllables: list[VariantList],
        constraints: ConstraintTable,
    ) -> list[str]:
        """Check one per-position constraint table and collect all mismatches.

        Args:
            all_syllables: One variant list per line.
            constraints: Per-position constraint table.

        Returns:
            List of error messages.

        """
        errors: list[str] = []
        min_constraint_lines = min(len(all_syllables), len(constraints))
        for i in range(min_constraint_lines):
            line_constraints = constraints[i]
            variants = all_syllables[i]
            if not variants:
                errors.append(
                    f"Line {i + 1} has no syllables; "
                    "cannot satisfy per-position constraints"
                )
                continue
            if any(
                MeterValidator._line_matches_variant(v, line_constraints)
                for v in variants
            ):
                continue
            syllables = variants[0]
            min_syl = min(len(syllables), len(line_constraints))
            for j in range(min_syl):
                if not syllables[j].match_constraint(line_constraints[j]):
                    errors.append(
                        f"Line {i + 1} syllable {j + 1} mismatch: required "
                        f"{MeterValidator._describe_constraint(line_constraints[j])}"
                        f", actual "
                        f"{MeterValidator._describe_syllable(syllables[j])}"
                    )
        return errors

    @staticmethod
    def _line_matches_variant(
        variant: list[Syllable], line_constraints: ConstraintLine
    ) -> bool:
        """Check whether a line's syllables satisfy all per-position constraints.

        Args:
            variant: One syllable division variant of a line.
            line_constraints: Per-position constraints for that line.

        Returns:
            True when all constraints are satisfied.

        """
        min_syl = min(len(variant), len(line_constraints))
        for j in range(min_syl):
            if not variant[j].match_constraint(line_constraints[j]):
                return False
        return True

    @staticmethod
    def _order_variants(
        language: str, variants: list[list[Syllable]]
    ) -> list[list[Syllable]]:
        """Sort the variants of a line for the combination search.

        The primary variant goes first, so it is the first combination tried.

        Args:
            language: Language code.
            variants: Candidate divisions for the line.

        Returns:
            Sorted variant list (primary variant first).

        """
        if language == "en":
            return sorted(
                variants,
                key=lambda v: sum(
                    1 for s in v if s.attributes.get("stress") == "heavy"
                ),
                reverse=True,
            )
        return variants

    def _validate_full_variants(
        self,
        template_obj: Any,
        poem: list[str],
        all_syllables: list[list[list[Syllable]]],
        language: str,
    ) -> list[str]:
        """Search combinations of all pronunciation/division variants per line.

        Accepts the poem when any combination passes every rule. Instead of
        using only the primary variant, each variant is fed into validate_full.
        If some per-line variant combination passes all meter rules, returns no
        errors; otherwise returns the errors of the combination with the fewest
        errors (falling back to each language's primary variant). When the
        number of combinations is too large it is truncated at
        ``MAX_FULL_COMBOS`` to avoid the explosion caused by Italian sinalefe /
        English multiple divisions.

        Args:
            template_obj: Template object (has validate_full).
            poem: Poem line text (used by text-level rules such as rhyme /
                refrain).
            all_syllables: One variant list per line (VariantList).
            language: Language code.

        Returns:
            Error list; empty when a valid combination exists.

        """
        line_variants: list[list[list[Syllable]]] = []
        for vs in all_syllables:
            if vs:
                line_variants.append(self._order_variants(language, list(vs)))
            else:
                line_variants.append([[]])
        best: list[str] | None = None
        best_len: int | None = None
        for tried, combo in enumerate(itertools.product(*line_variants), start=1):
            errs = template_obj.validate_full(poem, list(combo))
            if not errs:
                return []
            if best_len is None or len(errs) < best_len:
                best_len = len(errs)
                best = errs
            if tried >= MAX_FULL_COMBOS:
                break
        return best if best is not None else []

    def validate_count_only(
        self,
        poem: list[str],
        template: TemplateDict,
    ) -> ValidationResult:
        """Validate only the line count and syllables per line (quick check).

        Used for the early draft stage.

        Args:
            poem: List of poem lines.
            template: Template dictionary.

        Returns:
            Validation result.

        """
        language = str(template.get("language", "zh"))
        lines_expected = int(template.get("lines", len(poem)))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"Line count mismatch: expected {lines_expected} lines, "
                f"actual {len(poem)} lines"
            )

        min_lines = min(len(poem), len(syllables_expected))
        for i in range(min_lines):
            line = poem[i]
            expected_count = syllables_expected[i]
            # Same as full validation: take all pronunciation/division variants
            # of the line; any variant matching the syllable count passes.
            variants = get_analyzer(language).analyze_line_variants(line)
            ok = any(_count_matches(len(v), expected_count) for v in variants)
            actual_count = len(variants[0]) if variants else 0

            if not ok:
                result.add_error(
                    f"Line {i + 1} syllable count mismatch: "
                    f"expected {format_count(expected_count)}, "
                    f"actual {actual_count}"
                )

        return result

    def validate_line(
        self,
        line_text: str,
        line_index: int,
        template: TemplateDict,
    ) -> ValidationResult:
        """Validate a single line (pre-check for the modify tool's line type).

        Args:
            line_text: New line text.
            line_index: Line index (0-based).
            template: Template dictionary.

        Returns:
            Validation result.

        """
        language = str(template.get("language", "zh"))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )
        constraints_raw = template.get("syllable_constraints", [])
        alternatives = self._constraint_alternatives(template)
        constraints: ConstraintTable = list(constraints_raw) if constraints_raw else []

        result = ValidationResult()

        if line_index < len(syllables_expected):
            expected_count = syllables_expected[line_index]
            variants = get_analyzer(language).analyze_line_variants(line_text)
            ok = any(_count_matches(len(v), expected_count) for v in variants)
            actual_count = len(variants[0]) if variants else 0
            if not ok:
                result.add_error(
                    f"Syllable count mismatch: "
                    f"expected {format_count(expected_count)}, "
                    f"actual {actual_count}"
                )

        if alternatives:
            best_errors = self._best_line_alternative_errors(
                language, line_text, line_index, alternatives
            )
            if best_errors is not None:
                for err in best_errors:
                    result.add_error(err)
            return result

        if constraints and line_index < len(constraints):
            line_constraints = constraints[line_index]
            variants = get_analyzer(language).analyze_line_variants(line_text)
            if any(self._line_matches_variant(v, line_constraints) for v in variants):
                return result
            syllables = variants[0]
            min_syl = min(len(syllables), len(line_constraints))
            for j in range(min_syl):
                if not syllables[j].match_constraint(line_constraints[j]):
                    constraint_desc = self._describe_constraint(line_constraints[j])
                    actual_desc = self._describe_syllable(syllables[j])
                    result.add_error(
                        f"Syllable {j + 1}: required {constraint_desc}, "
                        f"actual {actual_desc}"
                    )

        return result

    def _best_line_alternative_errors(
        self,
        language: str,
        line_text: str,
        line_index: int,
        alternatives: list[ConstraintTable],
    ) -> list[str] | None:
        """Check how a single line matches multiple constraint tables (OR).

        Args:
            language: Language code.
            line_text: Line text.
            line_index: Line index (0-based).
            alternatives: Multiple constraint tables.

        Returns:
            When no table matches, the errors of the table with the fewest
            errors; None when a matching table exists (or the line is
            unconstrained).

        """
        variants = get_analyzer(language).analyze_line_variants(line_text)
        best: list[str] | None = None
        for table in alternatives:
            if line_index >= len(table):
                return None
            line_constraints = table[line_index]
            if not line_constraints:
                return None
            if any(self._line_matches_variant(v, line_constraints) for v in variants):
                return None
            errors: list[str] = []
            syllables = variants[0] if variants else []
            min_syl = min(len(syllables), len(line_constraints))
            for j in range(min_syl):
                if not syllables[j].match_constraint(line_constraints[j]):
                    errors.append(
                        f"Syllable {j + 1}: required "
                        f"{self._describe_constraint(line_constraints[j])}, "
                        f"actual {self._describe_syllable(syllables[j])}"
                    )
            if best is None or len(errors) < len(best):
                best = errors
        return best

    @staticmethod
    def _describe_constraint(c: Constraint) -> str:
        """Return a human-readable description of a constraint.

        Args:
            c: Constraint dictionary.

        Returns:
            For example "onset=zh,tone=平"; "no constraints" when empty.

        """
        parts = []
        if c.get("onset"):
            parts.append(f"onset={c['onset']}")
        if c.get("nucleus"):
            parts.append(f"nucleus={c['nucleus']}")
        if c.get("coda"):
            parts.append(f"coda={c['coda']}")
        for k, v in c.get("attributes", {}).items():
            if v:
                parts.append(f"{k}={v}")
        return ",".join(parts) if parts else "no constraints"

    @staticmethod
    def _describe_syllable(s: Syllable) -> str:
        """Return a human-readable description of a syllable.

        Args:
            s: Syllable.

        Returns:
            For example "onset=zh,tone=仄"; "empty" when all fields are empty.

        """
        parts = []
        if s.onset:
            parts.append(f"onset={s.onset}")
        if s.nucleus:
            parts.append(f"nucleus={s.nucleus}")
        if s.coda:
            parts.append(f"coda={s.coda}")
        for k, v in s.attributes.items():
            if v:
                parts.append(f"{k}={v}")
        return ",".join(parts) if parts else "empty"
