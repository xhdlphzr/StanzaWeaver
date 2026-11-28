# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Italian metrical templates: terza rima, ottava rima, canzone.

Defining feature of the eleven-syllable line (endecasillabo): its 10th syllable
must be stressed.
"""

from typing import ClassVar

from ..models.syllable import Syllable
from . import ConstraintTable, PoetryTemplate, register


def _check_tenth_syllable_stress(
    syllables: list[list[Syllable]],
    errors: list[str],
    indices: list[int] | None = None,
) -> None:
    """Check that the 10th syllable is stressed and the 11th is unstressed.

    Only applies to lines with enough syllables (given lines, or all by
    default): 10+ syllables need the 10th stressed; 11+ syllables also need the
    11th unstressed (to avoid misjudging tronca lines).

    Args:
        syllables: Syllables per line.
        errors: Error list (appended in place).
        indices: Only check these line numbers (0-based); all lines when None.

    """
    targets = indices if indices is not None else list(range(len(syllables)))
    for i in targets:
        syls = syllables[i]
        if len(syls) >= 10 and syls[9].attributes.get("stress") != "heavy":
            errors.append(f"Line {i + 1} syllable 10 should be stressed but is not")
        if len(syls) >= 11 and syls[10].attributes.get("stress") == "heavy":
            errors.append(f"Line {i + 1} syllable 11 should not be stressed")


def _check_last_syllable_stress(
    syllables: list[list[Syllable]],
    errors: list[str],
    indices: list[int] | None = None,
) -> None:
    """Check that the last syllable of the given lines is stressed (tronca ending).

    Args:
        syllables: Syllables per line.
        errors: Error list (appended in place).
        indices: Only check these line numbers (0-based); all lines when None.

    """
    targets = indices if indices is not None else list(range(len(syllables)))
    for i in targets:
        syls = syllables[i]
        if syls and syls[-1].attributes.get("stress") != "heavy":
            errors.append(f"Line {i + 1} last syllable should be stressed but is not")


def _check_rhyme_group(
    syllables: list[list[Syllable]], indices: list[int], label: str, errors: list[str]
) -> None:
    """Check that the last syllables of a set of lines rhyme (nucleus + coda).

    Args:
        syllables: Syllables per line.
        indices: Line numbers participating in this rhyme group (0-based).
        label: Rhyme group name.
        errors: Error list (appended in place).

    """
    rhymes: list[tuple[int, str]] = []
    for idx in indices:
        if idx < len(syllables) and syllables[idx]:
            r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
            if r:
                rhymes.append((idx, r))
    if len(rhymes) >= 2:
        base = rhymes[0][1]
        for idx, r in rhymes[1:]:
            if r != base:
                errors.append(
                    f"Rhyme {label} mismatch: line {rhymes[0][0] + 1} rhymes "
                    f"with '{base}', line {idx + 1} rhymes with '{r}'"
                )


class TerzaRimaTemplate(PoetryTemplate):
    """Terza rima: 14 eleven-syllable lines, interlocking rhyme ABA BCB CDC DED EE."""

    name = "三行体"
    language = "it"
    lines = 14
    special_rules = ("The 10th syllable must be stressed",)
    rhyme_scheme = "ABABCBCDCDEDEE"
    syllables_per_line: ClassVar[list[int]] = [11] * 14
    rule_description = (
        "Rules: 11 syllables per line (cross-word vowel elision, sinalefe, is "
        "merged into the count); the 10th syllable of every line must be "
        "stressed (the defining feature of the endecasillabo); rhyme scheme "
        "ABA BCB CDC DED EE (interlocking chain rhyme, each new rhyme "
        "differing from the preceding one)."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: 10th-syllable stress + interlocking rhyme scheme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        _check_tenth_syllable_stress(syllables, errors)
        rhyme_groups = [
            ([0, 2], "ABA"),
            ([1, 3, 5], "BCB"),
            ([4, 6, 8], "CDC"),
            ([7, 9, 11], "DED"),
            ([10, 12, 13], "EE"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(syllables, indices, label, errors)
        return errors


class OttavaRimaTemplate(PoetryTemplate):
    """Ottava rima: 8 eleven-syllable lines, ABABABCC scheme."""

    name = "八行体"
    language = "it"
    lines = 8
    special_rules = ("The 10th syllable must be stressed",)
    rhyme_scheme = "ABABABCC"
    syllables_per_line: ClassVar[list[int]] = [11] * 8
    rule_description = (
        "Rules: 11 syllables per line (cross-word vowel elision, sinalefe, is "
        "merged into the count); the 10th syllable of every line must be "
        "stressed; rhyme scheme ABABABCC (alternating rhyme over the first "
        "six lines, closing couplet CC)."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: 10th-syllable stress + ABABABCC scheme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        _check_tenth_syllable_stress(syllables, errors)
        rhyme_groups = [
            ([0, 2, 4], "A"),
            ([1, 3, 5], "B"),
            ([6, 7], "CC"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(syllables, indices, label, errors)
        return errors


class CanzoneTemplate(PoetryTemplate):
    """Canzone: 13 lines with alternating 11/7 syllable counts.

    Odd lines end unstressed; even lines and the final line end stressed; at
    most 4 rhymes are used.
    """

    name = "歌谣"
    language = "it"
    lines = 13
    special_rules = (
        "At most 4 rhymes are used",
        "The same rhyme does not occur more than 2 times in a row",
        "The final three lines each have a different rhyme",
        "The final syllable must be stressed",
    )
    syllables_per_line: ClassVar[list[int]] = [
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        7,
    ]
    rule_description = (
        "Rules: odd lines (1, 3, 5, 7, 9 and 11) have 11 syllables "
        "(endecasillabo femminile), with the 10th syllable stressed and the "
        "11th unstressed; even lines (2, 4, 6, 8, 10 and 12) and line 13 have "
        "7 syllables (settenario femminile), with a stressed final syllable; "
        "the poem uses the four rhymes A, B, C and D, the same rhyme may not "
        "occur more than twice in a row, and the final three lines each have "
        "a different rhyme."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: odd lines (11 syllables) syllable 10 stressed, 11 unstressed.

        Even lines and line 13 (7 syllables) end stressed; rhymes <=4,
        consecutive same rhymes <=2, final three lines all different.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        # Odd lines (1,3,5,7,9,11): 11 syllables; 10th stressed, 11th unstressed.
        _check_tenth_syllable_stress(syllables, errors, indices=[0, 2, 4, 6, 8, 10])
        # Even lines (2,4,6,8,10,12) and line 13: 7 syllables, last stressed.
        _check_last_syllable_stress(syllables, errors, indices=[1, 3, 5, 7, 9, 11, 12])

        distinct: set[str] = set()
        for syls in syllables:
            if syls:
                r = syls[-1].nucleus + syls[-1].coda
                if r:
                    distinct.add(r)
        if len(distinct) > 4:
            errors.append(
                f"The poem should use at most 4 rhymes but uses "
                f"{len(distinct)}: {sorted(distinct)}"
            )

        prev = ""
        streak = 0
        for idx, syls in enumerate(syllables):
            r = syls[-1].nucleus + syls[-1].coda if syls else ""
            if r and r == prev:
                streak += 1
                if streak >= 2:
                    errors.append(
                        f"Lines {idx - 1}, {idx} and {idx + 1} use the same "
                        f"rhyme three times in a row"
                    )
                    streak = 0
            else:
                streak = 0
            prev = r

        tails: list[str] = []
        for idx in (10, 11, 12):
            if idx < len(syllables) and syllables[idx]:
                tails.append(syllables[idx][-1].nucleus + syllables[idx][-1].coda)
        if len(tails) == 3 and len(set(tails)) < 3:
            errors.append(
                f"The final three lines must have different rhymes; got {tails}"
            )

        return errors


def register_italian_templates() -> None:
    """Register all Italian templates."""
    register("it_terza_rima", TerzaRimaTemplate())
    register("it_ottava_rima", OttavaRimaTemplate())
    register("it_canzone", CanzoneTemplate())
