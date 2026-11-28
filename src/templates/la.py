# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Latin metrical templates: hexameter, elegiac distich, hendecasyllable.

- Hexameter: feet 1-4 freely alternate dactyls/spondees, foot 5 must be a
  dactyl, foot 6 has 2 syllables (spondee or trochee).
- Elegiac distich: line 1 is a hexameter, line 2 a pentameter (its last 6
  syllables must be two complete dactyls).
- Hendecasyllable: foot 1's first syllable must be long, and a word boundary
  must occur between syllables 5 and 6.
"""

from typing import Any, ClassVar

from ..models.syllable import Syllable
from ..prosody.latin import LatinAnalyzer
from . import ConstraintTable, PoetryTemplate, _make_syl, register

_LATIN = LatinAnalyzer()


_L: dict[str, Any] = _make_syl(attributes={"length": "long"})
_S: dict[str, Any] = _make_syl(attributes={"length": "short"})


def _validate_hex(syls: list[Syllable]) -> list[str]:
    """Validate a hexameter line completely.

    Feet 1-4 freely alternate dactyls (long-short-short) and spondees
    (long-long); foot 5 must be a dactyl (long-short-short); foot 6 is a
    spondee or trochee (2 syllables).

    Args:
        syls: Syllables of one line.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    n = len(syls)
    if n < 13:
        errors.append(f"Not enough syllables: need at least 13, got {n}")
        return errors
    i = 0
    feet: list[tuple[int, int, int]] = []
    for foot_idx in range(4):
        if (
            i + 2 < n
            and syls[i + 1].attributes.get("length") == "short"
            and syls[i + 2].attributes.get("length") == "short"
        ):
            feet.append((foot_idx, i, i + 3))
            i += 3
        else:
            feet.append((foot_idx, i, i + 2))
            i += 2
    if i + 3 <= n:
        feet.append((4, i, i + 3))
        i += 3
    else:
        feet.append((4, i, n))
        i = n
    if i < n:
        feet.append((5, i, n))

    if len(feet) < 6:
        errors.append(f"Not enough feet: need 6 but only scanned {len(feet)}")
        return errors

    for foot_idx, start, end in feet:
        foot = syls[start:end]
        first_len = foot[0].attributes.get("length", "")
        if foot_idx < 4:
            if first_len != "long":
                errors.append(
                    f"Foot {foot_idx + 1} should start with a long syllable "
                    f"but starts with {first_len or 'unknown'}"
                )
            if len(foot) == 3:
                # A three-syllable foot must be a dactyl (the dactyl scan
                # already guarantees long-short-short), so no re-check needed.
                pass
            elif len(foot) == 2 and foot[1].attributes.get("length") != "long":
                errors.append(
                    f"Foot {foot_idx + 1} spondee should have two long "
                    f"syllables but the second is "
                    f"{foot[1].attributes.get('length') or 'unknown'}"
                )
        elif foot_idx == 4:
            if (
                first_len != "long"
                or foot[1].attributes.get("length") != "short"
                or foot[2].attributes.get("length") != "short"
            ):
                errors.append("Foot 5 must be a dactyl (long-short-short)")
        else:
            if len(foot) != 2:
                errors.append(
                    f"Foot 6 should have 2 syllables (spondee or trochee) "
                    f"but has {len(foot)}"
                )
            elif first_len != "long":
                errors.append(
                    f"Foot 6 should start with a long syllable but starts "
                    f"with {first_len or 'unknown'}"
                )
    return errors


class HexameterTemplate(PoetryTemplate):
    """Hexameter: a single line, stackable, validated line by line."""

    name = "Hexameter"
    language = "la"
    lines = 1
    special_rules = ("Six-foot structure", "Foot 5 must be a dactyl")
    syllables_per_line: ClassVar[list[tuple[int, int]]] = [(13, 17)]
    rule_description = (
        "Rules: 6 feet in total; feet 1-4 may freely alternate between "
        "dactyls (long-short-short) and spondees (long-long); foot 5 must be "
        "a dactyl (long-short-short); foot 6 is a spondee or trochee, and its "
        "final syllable may be long or short; quantity determination: "
        "dictionary markings take precedence, and when unmarked a diphthong "
        "or a vowel followed by two or more consonants (including across "
        "words) counts as long."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed-position constraints (feet may be substituted; validate_full scans).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Validate hexameter structure foot by foot.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        if syllables and syllables[0]:
            errors.extend(_validate_hex(syllables[0]))
        return errors


class DistichonTemplate(PoetryTemplate):
    """Elegiac distich: line 1 is a hexameter, line 2 a pentameter.

    The last 6 syllables of line 2 are two complete dactyls.
    """

    name = "Elegiac Distich"
    language = "la"
    lines = 2
    special_rules = (
        "Hexameter/pentameter foot structure",
        "The last 6 syllables of line 2 must be two dactyls",
        "Mid-line caesura in line 2",
    )
    rhyme_scheme = "AA"
    syllables_per_line: ClassVar[list[tuple[int, int]]] = [(13, 17), (11, 13)]
    rule_description = (
        "Rules: line 1 follows the hexameter rules exactly; line 2 is a "
        "pentameter: its first 2.5 feet may be dactyls or spondees (free), a "
        "caesura is required in the middle, and its last 2.5 feet must close "
        "with two complete dactyls (long-short-short long-short-short); the "
        "final words of the two lines must rhyme (AA)."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed-position constraints (same as hexameter).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    @staticmethod
    def _has_pentameter_caesura(line: str, total: int) -> bool:
        """Check whether a caesura (word boundary) divides the pentameter in two.

        The second half of a pentameter is two complete dactyls (6 syllables),
        so the caesura must fall on a word boundary after ``total - 6``
        syllables.

        Args:
            line: Text of line 2 (the pentameter).
            total: Total syllable count of the line.

        Returns:
            True when a word boundary separates the two halves, else False.

        """
        if total < 6:
            return False
        split = total - 6
        cum = 0
        for w in line.split():
            w_clean = w.strip(".,;:!?\"'()[]{}")
            if not w_clean:
                continue
            n = len(_LATIN.analyze_word(w_clean))
            if cum + n == split:
                return True
            cum += n
        return False

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: line 1 hexameter, line 2 last 6 syllables dactyl x2.

        Also checks the mid-line caesura and the AA rhyme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        if not syllables or len(syllables) < 2:
            return errors
        if syllables[0]:
            errors.extend(_validate_hex(syllables[0]))
        pent_syls = syllables[1]
        if len(pent_syls) >= 6:
            tail = pent_syls[-6:]
            expected = ["long", "short", "short", "long", "short", "short"]
            for j, (s, exp) in enumerate(zip(tail, expected)):
                actual = s.attributes.get("length", "")
                if actual and actual != exp:
                    errors.append(
                        f"Line 2 syllable {6 - j} from the end should be "
                        f"{exp} (the last 2.5 feet must be two complete "
                        f"dactyls) but is {actual}"
                    )
            line2 = poem[1] if len(poem) > 1 else ""
            if not self._has_pentameter_caesura(line2, len(pent_syls)):
                errors.append(
                    "Pentameter line 2 lacks a mid-line caesura: a word "
                    "boundary is required between the first 2.5 feet and the "
                    "last 2.5 feet"
                )
        elif len(pent_syls) >= 2:
            errors.append("Line 2 has too few syllables: at least 11 required")
        if len(poem) >= 2 and syllables[0] and syllables[1]:
            r0 = syllables[0][-1].nucleus + syllables[0][-1].coda
            r1 = syllables[1][-1].nucleus + syllables[1][-1].coda
            if r0 and r1 and r0 != r1:
                errors.append(
                    f"Rhyme mismatch: line 1 rhymes with '{r0}', line 2 "
                    f"rhymes with '{r1}'"
                )
        return errors


class HendecasyllabusTemplate(PoetryTemplate):
    """Hendecasyllable: 5 feet, with a word boundary between syllables 5 and 6."""

    name = "Hendecasyllable"
    language = "la"
    lines = 1
    special_rules = (
        "Hendecasyllable foot structure",
        "A word boundary is required between syllables 5 and 6",
    )
    syllables_per_line: ClassVar[list[int]] = [11]
    rule_description = (
        "Rules: 5 feet and 11 syllables in total; foot 1 is a spondee or "
        "trochee (its first syllable must be long); foot 2 is always a dactyl "
        "(long-short-short); feet 3-5 are all trochees (long-short); a foot "
        "boundary (no word may cross it) is required between syllables 5 and "
        "6 of the line; syllables 3, 5, 6, 8 and 10 of the line must be long."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed foot-pattern constraints (foot 1's first syllable must be long).

        Returns:
            Per-position syllable constraint table.

        """
        return [
            [
                _L,
                {},
                _L,
                _S,
                _L,
                _L,
                _S,
                _L,
                _S,
                _L,
                _S,
            ]
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: fixed long positions + word boundary between syllables 5/6.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        if not syllables or not syllables[0]:
            return errors
        syls = syllables[0]
        if len(syls) < 11:
            errors.append(f"Not enough syllables: need 11 but got {len(syls)}")
        patterns = [
            (2, "long"),
            (4, "long"),
            (5, "long"),
            (7, "long"),
            (9, "long"),
        ]
        for pos, expected in patterns:
            if pos < len(syls):
                actual = syls[pos].attributes.get("length", "")
                if actual and actual != expected:
                    errors.append(f"Syllable {pos + 1} should be long but is {actual}")

        if poem:
            line = poem[0]
            cum = 0
            boundary_ok = False
            for w in line.split():
                w_clean = w.strip(".,;:!?\"'()[]{}")
                if not w_clean:
                    continue
                n = len(_LATIN.analyze_word(w_clean))
                if cum + n == 5:
                    boundary_ok = True
                    break
                cum += n
            if not boundary_ok:
                errors.append(
                    "Syllables 5 and 6 must be separated by a foot boundary "
                    "(word boundary); it is missing"
                )
        return errors


def register_latin_templates() -> None:
    """Register all Latin templates."""
    register("la_hexameter", HexameterTemplate())
    register("la_distichon", DistichonTemplate())
    register("la_hendecasyllabus", HendecasyllabusTemplate())
