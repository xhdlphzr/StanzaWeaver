# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Data-driven structural rule validation (carried across language conversion).

The rules of regulated verse (quatrains and regulated poems) used to live only
inside template classes: level/oblique alternation, opposition and adhesion,
tail tones of opening and couplet lines, three level-tone tail, isolated level,
and level-tone rhyme. These rules only depend on "some attribute value"
(level/oblique tones in Chinese, heavy/light in English, ...), so they can be
expressed as a ``structural_rules`` description and validated uniformly by
this module:

    {
        "kind": "jinti",
        "attribute": "tone",          # syllable attribute key
        "level_value": "平",
        "oblique_value": "仄",
        "positions": [1, 3],           # fixed positions to alternate (0-based)
        "rhyme_lines": [1, 3],         # lines that must rhyme (0-based)
        "optional_first_rhyme": True,  # first line rhymes if level_value
        "forbid_sanpingwei": True,     # forbid three level-tone tail
        "forbid_guping": True,          # forbid isolated level
    }

During conversion, only ``attribute``/``level_value``/``oblique_value`` are
remapped to the target language's attribute and values; all other fields are
copied verbatim, and the rule then takes effect in the new language.
"""

from typing import Any

from ..models.syllable import Syllable
from .rhyme import rhyme_keys

#: Kinds allowed for structural rules (currently only regulated verse).
STRUCTURAL_KINDS: tuple[str, ...] = ("jinti",)

#: Legal keys of a structural-rule dict.
STRUCTURAL_KEYS: tuple[str, ...] = (
    "kind",
    "attribute",
    "level_value",
    "oblique_value",
    "positions",
    "rhyme_lines",
    "optional_first_rhyme",
    "forbid_sanpingwei",
    "forbid_guping",
)


def _as_int_list(value: Any) -> list[int] | None:
    """Convert an arbitrary value to a list of non-negative integers.

    Args:
        value: Raw value.

    Returns:
        Integer list; None when invalid.

    """
    if not isinstance(value, (list, tuple)):
        return None
    result: list[int] = []
    for item in value:
        try:
            number = int(item)
        except TypeError, ValueError:
            return None
        if number < 0:
            return None
        result.append(number)
    return result


def normalize_structural_rules(
    raw: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and normalize structural-rule data (for the template API and AI drafts).

    Args:
        raw: Raw structural rules (may be None).

    Returns:
        (Normalized rules or None, error message); error is None when valid.

    """
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, "structural_rules must be an object"
    kind = str(raw.get("kind", "")).strip()
    if kind not in STRUCTURAL_KINDS:
        return None, f"Unknown structural rule kind {kind!r}"
    attribute = str(raw.get("attribute", "")).strip()
    level_value = str(raw.get("level_value", "")).strip()
    oblique_value = str(raw.get("oblique_value", "")).strip()
    if not attribute or not level_value or not oblique_value:
        return None, "Structural rules are missing attribute/level_value/oblique_value"
    positions = _as_int_list(raw.get("positions"))
    rhyme_lines = _as_int_list(raw.get("rhyme_lines"))
    if not positions or not rhyme_lines:
        return None, "Structural rules are missing positions/rhyme_lines"
    return (
        {
            "kind": kind,
            "attribute": attribute,
            "level_value": level_value,
            "oblique_value": oblique_value,
            "positions": positions,
            "rhyme_lines": rhyme_lines,
            "optional_first_rhyme": bool(raw.get("optional_first_rhyme", False)),
            "forbid_sanpingwei": bool(raw.get("forbid_sanpingwei", False)),
            "forbid_guping": bool(raw.get("forbid_guping", False)),
        },
        None,
    )


def _value_at(syllables: list[Syllable], position: int, attribute: str) -> str:
    """Get the attribute value at a fixed position of a line.

    Args:
        syllables: Syllables of one line.
        position: Position (0-based).
        attribute: Attribute key.

    Returns:
        Attribute value; empty string when out of range or unknown.

    """
    if position < 0 or position >= len(syllables):
        return ""
    return str(syllables[position].attributes.get(attribute, "") or "")


def _last_value(syllables: list[Syllable], attribute: str) -> str:
    """Get the attribute value of a line's last syllable.

    Args:
        syllables: Syllables of one line.
        attribute: Attribute key.

    Returns:
        Attribute value; empty string for an empty line.

    """
    if not syllables:
        return ""
    return str(syllables[-1].attributes.get(attribute, "") or "")


def check_jinti_rules(
    language: str,
    poem: list[str],
    syllables: list[list[Syllable]],
    rules: dict[str, Any],
) -> list[str]:
    """Validate a whole poem against data-driven regulated-verse rules.

    Args:
        language: Language code (determines how rhyme keys are computed).
        poem: Poem line texts.
        syllables: Syllables per line.
        rules: Normalized structural rules (see module docstring).

    Returns:
        List of error messages; empty when everything passes.

    """
    errors: list[str] = []
    if not syllables or len(syllables) < 2:
        return errors
    attribute = str(rules.get("attribute", ""))
    level = str(rules.get("level_value", ""))
    oblique = str(rules.get("oblique_value", ""))
    positions = [int(p) for p in rules.get("positions", [])]
    rhyme_lines = [int(p) for p in rules.get("rhyme_lines", [])]
    forbid_sanpingwei = bool(rules.get("forbid_sanpingwei", False))
    forbid_guping = bool(rules.get("forbid_guping", False))
    optional_first_rhyme = bool(rules.get("optional_first_rhyme", False))

    fixed_positions = [
        position
        for position in positions
        if not syllables[0] or position < len(syllables[0])
    ]

    for i, line_syllables in enumerate(syllables):
        if not line_syllables:
            continue
        last_value = _last_value(line_syllables, attribute)
        if forbid_sanpingwei and len(line_syllables) >= 3:
            tail = [
                _value_at(line_syllables, len(line_syllables) - k, attribute)
                for k in (3, 2, 1)
            ]
            if level and tail == [level, level, level]:
                errors.append(
                    f"Line {i + 1} has three level-tone tail: "
                    f"last three syllables are all '{level}'"
                )
        if forbid_guping and level and last_value == level:
            level_count = sum(
                1
                for syl in line_syllables
                if str(syl.attributes.get(attribute, "") or "") == level
            )
            if level_count == 1:
                errors.append(
                    f"Line {i + 1} has isolated level: the level-ending line "
                    f"contains only one '{level}' syllable"
                )

    prev_inner: list[str] | None = None
    for i in range(0, len(syllables) - 1, 2):
        outer = [
            _value_at(syllables[i], position, attribute) for position in fixed_positions
        ]
        inner = [
            _value_at(syllables[i + 1], position, attribute)
            for position in fixed_positions
        ]
        if i >= 2 and syllables[i] and _last_value(syllables[i], attribute) == level:
            errors.append(
                f"Line {i + 1} is a leading line; its last syllable should be "
                f"'{oblique}' but is '{level}'"
            )
        if syllables[i + 1] and _last_value(syllables[i + 1], attribute) == oblique:
            errors.append(
                f"Line {i + 2} is a responding line; its last syllable should be "
                f"'{level}' but is '{oblique}'"
            )

        for j in range(len(fixed_positions) - 1):
            for index, values in ((i, outer), (i + 1, inner)):
                first = values[j] if j < len(values) else ""
                second = values[j + 1] if j + 1 < len(values) else ""
                if first and second and first == second:
                    errors.append(
                        f"Line {index + 1} syllables {fixed_positions[j] + 1} and "
                        f"{fixed_positions[j + 1] + 1} should alternate in "
                        f"level/oblique but are both '{first}'"
                    )
        for j, (first, second) in enumerate(zip(outer, inner)):
            if first and second and first == second:
                errors.append(
                    f"Lines {i + 1} and {i + 2} should oppose: syllable "
                    f"{fixed_positions[j] + 1} should have the opposite "
                    f"level/oblique but both are '{first}'"
                )
        if prev_inner is not None:
            for j, (first, second) in enumerate(zip(prev_inner, outer)):
                if first and second and first != second:
                    errors.append(
                        f"Line {i + 1} should adhere to line {i}: syllable "
                        f"{fixed_positions[j] + 1} should have the same "
                        f"level/oblique but is '{first}' and '{second}'"
                    )
        prev_inner = inner

    rhyme_keys_list: list[tuple[int, set[str]]] = []
    for index in rhyme_lines:
        if index >= len(syllables) or not syllables[index]:
            continue
        last_value = _last_value(syllables[index], attribute)
        if level and last_value != level:
            errors.append(
                f"Line {index + 1} rhyme should be '{level}' but is "
                f"'{last_value or 'unknown'}'"
            )
        keys = rhyme_keys(language, poem[index], syllables[index])
        if keys is not None:
            rhyme_keys_list.append((index, keys))
    if (
        optional_first_rhyme
        and syllables
        and syllables[0]
        and level
        and _last_value(syllables[0], attribute) == level
    ):
        keys = rhyme_keys(language, poem[0], syllables[0])
        if keys is not None:
            rhyme_keys_list.insert(0, (0, keys))
    if len(rhyme_keys_list) >= 2:
        common = set(rhyme_keys_list[0][1])
        for _, keys in rhyme_keys_list[1:]:
            common &= keys
        if not common:
            first_index, first_keys = rhyme_keys_list[0]
            last_index, last_keys = rhyme_keys_list[-1]
            errors.append(
                f"Rhyme mismatch: line {first_index + 1} rhymes with "
                f"'{'/'.join(sorted(key.split(':', 1)[-1] for key in first_keys))}', "
                f"line {last_index + 1} rhymes with "
                f"'{'/'.join(sorted(key.split(':', 1)[-1] for key in last_keys))}'; "
                f"they do not rhyme"
            )
    return errors
