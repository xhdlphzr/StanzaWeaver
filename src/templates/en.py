# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""English metrical templates: Shakespearean sonnet, villanelle, heroic couplet.

Rhyme uses strict stress matching: the rhyme must fall on a primary/secondary
stressed syllable, and all phonemes from that syllable on (including the stress
level) must match exactly; any pronunciation that satisfies the rhyme passes
(implemented by ``EnglishAnalyzer.rhyme_tails``).
"""

from typing import Any, ClassVar

from ..models.syllable import Syllable
from ..prosody.english import EnglishAnalyzer
from . import ConstraintTable, PoetryTemplate, _last_word, _make_syl, register

_EN_ANALYZER = EnglishAnalyzer()


_l: dict[str, Any] = _make_syl(attributes={"stress": "light"})
_h: dict[str, Any] = _make_syl(attributes={"stress": "heavy"})


def _en_last_word(line: str) -> str:
    """Get the last word of a line (punctuation stripped, lowercased).

    Args:
        line: One line of poetry.

    Returns:
        Last word of the line; empty string for an empty line.

    """
    return _last_word(line, "A-Za-z0-9'-")


def _en_rhyme_key(line_text: str) -> tuple[str, ...] | None:
    """Strict stress rhyme key: phoneme tails from the stressed syllable onward.

    Rhyme must be strict stress matching (including the stress level), and any
    pronunciation that satisfies the rhyme passes, so this returns a tuple of
    deduplicated tails (hashable for set operations).

    Args:
        line_text: One line of poetry.

    Returns:
        Tuple of rhyme tails; None when the last word has no stressed syllable
        (it cannot serve as a rhyme).

    """
    word = _en_last_word(line_text)
    if not word:
        return None
    tails = _EN_ANALYZER.rhyme_tails(word)
    if not tails:
        return None
    return tuple(sorted(set(tails)))


def _check_stress_count(
    poem: list[str], syllables: list[list[Syllable]], min_stress: int, errors: list[str]
) -> None:
    """Check the minimum stressed-syllable count of each line (secondary counts).

    Args:
        poem: List of poem lines.
        syllables: Syllables per line.
        min_stress: Minimum number of stressed syllables.
        errors: Error list (appended in place).

    """
    for i, syls in enumerate(syllables):
        stress_count = sum(1 for s in syls if s.attributes.get("stress") == "heavy")
        if stress_count < min_stress:
            errors.append(
                f"Line {i + 1} has too few stressed syllables ({stress_count})"
            )


def _check_rhyme_group(
    poem: list[str], indices: list[int], label: str, errors: list[str]
) -> None:
    """Check that a set of lines rhyme strictly by stress (shared tails).

    Args:
        poem: List of poem lines.
        indices: Line numbers participating in this rhyme group (0-based).
        label: Rhyme group name (A/B/AA, ...).
        errors: Error list (appended in place).

    """
    keys: list[tuple[int, tuple[str, ...]]] = []
    for idx in indices:
        if idx >= len(poem):
            continue
        k = _en_rhyme_key(poem[idx])
        if k is None:
            errors.append(
                f"Line {idx + 1} rhyme does not fall on a primary or secondary "
                f"stressed syllable"
            )
            continue
        keys.append((idx, k))
    if len(keys) >= 2:
        common: set[str] = set(keys[0][1])
        for _, k in keys[1:]:
            common &= set(k)
        if not common:
            first_idx, first_key = keys[0]
            last_idx, last_key = keys[-1]
            errors.append(
                f"Rhyme {label} mismatch: line {first_idx + 1} rhyme "
                f"{first_key}, line {last_idx + 1} rhyme {last_key} "
                f"(all lines in the group must share a phoneme tail starting "
                f"from a stressed syllable)"
            )


class ShakespeareSonnetTemplate(PoetryTemplate):
    """Shakespearean sonnet: 14 lines of iambic pentameter, ABAB CDCD EFEF GG."""

    name = "莎士比亚商籁体"
    language = "en"
    lines = 14
    special_rules = (
        "Each line has at least 4 stressed syllables",
        "Within each quatrain the A and B rhymes must differ",
    )
    rhyme_scheme = "ABABCDCDEFEFGG"
    syllables_per_line: ClassVar[list[int]] = [10] * 14
    rule_description = (
        "Rules: each line is iambic pentameter (10 syllables, with stress on "
        "the even positions; secondary stress also counts as stressed); rhyme "
        "scheme ABAB CDCD EFEF GG; within each quatrain the A and B rhymes "
        "must differ; rhyme must be strict stress rhyme: the rhyme foot must "
        "fall on a primary or secondary stressed syllable, and all phonemes "
        "from that syllable onward (including the stress level) must be "
        "exactly the same."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Iambic per-position constraints: light on odd positions, heavy on even.

        Returns:
            Per-position syllable constraint table.

        """
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line for _ in range(14)]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: stress minimum, ABAB CDCD EFEF GG scheme, distinct A/B.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        _check_stress_count(poem, syllables, 4, errors)

        rhyme_groups = [
            ("A", [0, 2], 0),
            ("B", [1, 3], 0),
            ("C", [4, 6], 1),
            ("D", [5, 7], 1),
            ("E", [8, 10], 2),
            ("F", [9, 11], 2),
            ("G", [12, 13], 3),
        ]
        quatrain_rhymes: dict[int, dict[str, tuple[str, ...] | None]] = {}
        for letter, indices, q_idx in rhyme_groups:
            if q_idx not in quatrain_rhymes:
                quatrain_rhymes[q_idx] = {}
            _check_rhyme_group(poem, indices, letter, errors)
            for idx in indices:
                if idx < len(poem):
                    quatrain_rhymes[q_idx][letter] = _en_rhyme_key(poem[idx])

        for q_idx in range(3):
            values = quatrain_rhymes.get(q_idx, {})
            present = [v for v in values.values() if v is not None]
            if len(present) >= 2:
                for i in range(len(present)):
                    for j in range(i + 1, len(present)):
                        if not set(present[i]).isdisjoint(present[j]):
                            errors.append(
                                f"Quatrain {q_idx + 1} rhyme: A/B rhymes should "
                                f"differ but share the tail "
                                f"{set(present[i]) & set(present[j])}"
                            )

        return errors


class VillanelleTemplate(PoetryTemplate):
    """Villanelle: 19 lines, ABA...ABAA scheme, two cycling refrains, free length."""

    name = "维拉内拉诗"
    language = "en"
    lines = 19
    special_rules = (
        "Each line has at least 4 stressed syllables",
        "Refrains must be repeated verbatim",
        "The A and B rhymes must differ",
    )
    rhyme_scheme = "ABAABAABAABAABAABAA"
    syllables_per_line: ClassVar[list[int | tuple[int, int]]] = []
    rule_description = (
        "Rules: 19 lines in total (5 tercets + 1 quatrain); rhyme scheme "
        "ABA ABA ABA ABA ABA ABAA; line 1 (A1) repeats verbatim at lines 6, "
        "12 and 18, and line 3 (A2) repeats verbatim at lines 9, 15 and 19; "
        "each line has at least 4 stressed syllables, with no restriction on "
        "the total syllable count (secondary stress also counts as stressed); "
        "rhyme must be strict stress rhyme: the rhyme foot falls on a primary "
        "or secondary stressed syllable, and all phonemes from that syllable "
        "onward (including the stress level) must be exactly the same."
    )
    _refrain_a1: ClassVar[list[int]] = [0, 5, 11, 17]
    _refrain_a2: ClassVar[list[int]] = [2, 8, 14, 18]
    _rhyme_a: ClassVar[list[int]] = [0, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    _rhyme_b: ClassVar[list[int]] = [1, 4, 7, 10, 13, 16]

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No per-position constraints (only require >=4 stressed syllables per line).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: stress minimum, verbatim refrains, A/B rhymes and distinctness.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        _check_stress_count(poem, syllables, 4, errors)

        if len(poem) > 0:
            base_a1 = _norm_refrain(poem[0])
            for ref_idx in self._refrain_a1[1:]:
                if ref_idx < len(poem) and _norm_refrain(poem[ref_idx]) != base_a1:
                    errors.append(
                        f"Refrain A1 mismatch: line 1 and line {ref_idx + 1} "
                        f"texts differ"
                    )
        if len(poem) > 2:
            base_a2 = _norm_refrain(poem[2])
            for ref_idx in self._refrain_a2[1:]:
                if ref_idx < len(poem) and _norm_refrain(poem[ref_idx]) != base_a2:
                    errors.append(
                        f"Refrain A2 mismatch: line 3 and line {ref_idx + 1} "
                        f"texts differ"
                    )

        _check_rhyme_group(poem, self._rhyme_a, "A", errors)
        _check_rhyme_group(poem, self._rhyme_b, "B", errors)

        a_key = _en_rhyme_key(poem[0]) if poem else None
        b_key = _en_rhyme_key(poem[1]) if len(poem) > 1 else None
        if a_key and b_key and not set(a_key).isdisjoint(b_key):
            errors.append(
                f"A/B rhymes should differ but share the tail {set(a_key) & set(b_key)}"
            )

        return errors


def _norm_refrain(line: str) -> str:
    """Normalize a refrain: collapse whitespace and ignore case.

    Args:
        line: One line of poetry.

    Returns:
        Normalized text.

    """
    return " ".join(line.split()).casefold()


class HeroicCoupletTemplate(PoetryTemplate):
    """Heroic couplet: two lines of iambic pentameter, strict AA stress rhyme.

    Couplets can be stacked continuously.
    """

    name = "英雄双行体"
    language = "en"
    lines = 2
    special_rules = ("Each line has at least 4 stressed syllables",)
    rhyme_scheme = "AA"
    syllables_per_line: ClassVar[list[int]] = [10, 10]
    rule_description = (
        "Rules: each line is iambic pentameter (10 syllables), with at least "
        "4 stressed syllables per line (secondary stress also counts as "
        "stressed); the final words of the two lines rhyme with each other "
        "(AA), and rhyme must be strict stress rhyme: the rhyme foot falls on "
        "a primary or secondary stressed syllable, and all phonemes from that "
        "syllable onward (including the stress level) must be exactly the "
        "same."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Iambic per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line, line]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: stress minimum + AA rhyme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        _check_stress_count(poem, syllables, 4, errors)
        _check_rhyme_group(poem, [0, 1], "AA", errors)
        return errors


def register_english_templates() -> None:
    """Register all English templates."""
    register("en_sonnet", ShakespeareSonnetTemplate())
    register("en_villanelle", VillanelleTemplate())
    register("en_heroic_couplet", HeroicCoupletTemplate())
