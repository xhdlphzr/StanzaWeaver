# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""French metrical templates: rondeau, triolet, ballade.

Rhyme uses ``FrenchAnalyzer.rhyme_key``: the final pronounced vowel nucleus
(nasalized merged), dropping silent final consonants (s/t/x/p, ...).
"""

from typing import ClassVar

from ..models.syllable import Syllable
from ..prosody.french import FrenchAnalyzer
from . import ConstraintTable, PoetryTemplate, _last_word, register

_FR = FrenchAnalyzer()


def _fr_last_word(line: str) -> str:
    """Get the last word of a line (punctuation stripped, lowercased).

    Args:
        line: One line of poetry.

    Returns:
        Last word of the line; empty string for an empty line.

    """
    return _last_word(line, "a-zA-Zàâäéèêëîïôöùûüÿœ'-")


def _check_rhyme_group(
    poem: list[str], indices: list[int], label: str, errors: list[str]
) -> None:
    """Check that the last words of a set of lines rhyme in French.

    Args:
        poem: List of poem lines.
        indices: Line numbers participating in this rhyme group (0-based).
        label: Rhyme group name.
        errors: Error list (appended in place).

    """
    keys: list[tuple[int, str]] = []
    for idx in indices:
        if idx >= len(poem):
            continue
        w = _fr_last_word(poem[idx])
        k = _FR.rhyme_key(w) if w else ""
        if k:
            keys.append((idx, k))
    if len(keys) >= 2:
        base = keys[0][1]
        for idx, k in keys[1:]:
            if k != base:
                errors.append(
                    f"Rhyme {label} mismatch: line {keys[0][0] + 1} rhymes "
                    f"with '{base}', line {idx + 1} rhymes with '{k}'"
                )


class RondeauTemplate(PoetryTemplate):
    """Rondeau: 15 lines in three stanzas, AABBA AAB AABBA, refrains on 9 and 15."""

    name = "回旋诗"
    language = "fr"
    lines = 15
    special_rules = ("Refrains must be repeated verbatim",)
    rhyme_scheme = "AABBAAABAAABBAA"
    # Each line allows 8 or 10 syllables (classic rondeaux use 10 throughout).
    syllables_per_line: ClassVar[list[int | tuple[int, int]]] = [(8, 10)] * 15
    _refrain_lines: ClassVar[list[int]] = [8, 14]  # 0-based: refrains on lines 9, 15
    rule_description = (
        "Rules: 15 lines in three stanzas (5+4+6); rhyme scheme "
        "AABBA AAB AABBA (only the two rhymes A and B are used); each line "
        "has 8 syllables (may be relaxed to 10, but must be uniform across "
        "the whole poem); the first half-line of line 1 repeats verbatim at "
        "the end of lines 9 and 15 as a refrain."
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
        """Full check: AABBA AAB AABBA scheme + first 4 refrain words match.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        rhyme_groups = [
            ([0, 1, 4, 5, 6, 8, 9, 10, 13, 14], "A"),
            ([2, 3, 7, 11, 12], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        base_refrain = poem[0] if len(poem) > 0 else ""
        for ref_idx in self._refrain_lines:
            if ref_idx < len(poem):
                first_words = " ".join(base_refrain.split()[:4])
                last_words = " ".join(poem[ref_idx].split()[-4:])
                if first_words and last_words and first_words != last_words:
                    errors.append(
                        f"Refrain mismatch: line 1 begins with '{first_words}' "
                        f"but line {ref_idx + 1} ends with '{last_words}'"
                    )
        return errors


class TrioletTemplate(PoetryTemplate):
    """Triolet: 8 lines, ABaAabAB scheme, lines 1/4/7 and 2/8 are refrains."""

    name = "三韵叠句诗"
    language = "fr"
    lines = 8
    special_rules = ("Refrains must be repeated verbatim",)
    rhyme_scheme = "ABAAABAB"
    syllables_per_line = [8] * 8
    rule_description = (
        "Rules: 8 lines of 8 syllables each; rhyme scheme ABaAabAB: lines 1, "
        "4 and 7 are the same A refrain repeated verbatim, and lines 2 and 8 "
        "are the same B refrain repeated verbatim; lines 3 and 5 rhyme on A "
        "(a), and line 6 rhymes on B (b)."
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
        """Full check: verbatim refrains (1=4=7, 2=8) + ABaAabAB scheme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        if len(poem) >= 8:
            if poem[0].strip() != poem[3].strip():
                errors.append("Refrain mismatch: line 1 and line 4 texts differ")
            if poem[0].strip() != poem[6].strip():
                errors.append("Refrain mismatch: line 1 and line 7 texts differ")
            if poem[1].strip() != poem[7].strip():
                errors.append("Refrain mismatch: line 2 and line 8 texts differ")
        rhyme_groups = [
            ([0, 2, 3, 4, 6], "A"),
            ([1, 5, 7], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        return errors


class BalladeTemplate(PoetryTemplate):
    """Ballade: 28 lines (3 stanzas of 8 + 4-line envoi), ababbcbc, final refrain."""

    name = "叙事歌"
    language = "fr"
    lines = 28
    special_rules = (
        "Refrains must be repeated verbatim",
        "Syllable counts must be uniform throughout the poem",
    )
    rhyme_scheme = "ABABBCBCABABBCBCABABBCBCBCBC"
    syllables_per_line: ClassVar[list[int | tuple[int, int]]] = []
    _refrain_line = 27
    rule_description = (
        "Rules: 28 lines (3 stanzas of 8 lines + a 4-line envoi); each "
        "stanza rhymes ababbcbc, and the three stanzas and the envoi use the "
        "same three rhymes A, B and C; the last line of each stanza (lines 8, "
        "16 and 24) and the last line of the envoi (line 28) are an identical "
        "refrain; every line of the poem has a uniform syllable count of 8 or "
        "10."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No per-position constraints (syllable counts are checked in validate_full).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: uniform syllables (8 or 10), ababbcbc scheme, refrains.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        counts = [len(s) for s in syllables if s]
        if counts:
            base = counts[0]
            if base not in (8, 10):
                errors.append(
                    f"Each ballade line should have 8 or 10 syllables; "
                    f"the first line has {base}"
                )
            for i, c in enumerate(counts):
                if c != base:
                    errors.append(
                        f"Line {i + 1} syllable count differs: expected {base}, got {c}"
                    )

        # Each stanza has 8 lines of ababbcbc; the envoi has 4 lines of bcbc
        # (0-based line numbers listed below).
        rhyme_a = [0, 2, 8, 10, 16, 18]
        rhyme_b = [1, 3, 4, 6, 9, 11, 12, 14, 17, 19, 20, 22, 24, 26]
        rhyme_c = [5, 7, 13, 15, 21, 23, 25, 27]

        for label, indices in [("A", rhyme_a), ("B", rhyme_b), ("C", rhyme_c)]:
            _check_rhyme_group(poem, indices, label, errors)

        if len(poem) > 27:
            base_refrain = poem[7]
            if poem[15].strip() != base_refrain.strip():
                errors.append("Refrain mismatch: line 8 and line 16 texts differ")
            if poem[23].strip() != base_refrain.strip():
                errors.append("Refrain mismatch: line 8 and line 24 texts differ")
            if poem[27].strip() != base_refrain.strip():
                errors.append("Refrain mismatch: line 8 and line 28 texts differ")
        return errors


def register_french_templates() -> None:
    """Register all French templates."""
    register("fr_rondeau", RondeauTemplate())
    register("fr_triolet", TrioletTemplate())
    register("fr_ballade", BalladeTemplate())
