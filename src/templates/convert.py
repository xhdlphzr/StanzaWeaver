# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unified template conversion interface (cross-language conversion).

The full spec a template exposes includes: line count, syllables per line,
per-position constraints (possibly several alternatives), rhyme scheme, and
custom validation code. During cross-language conversion, everything except the
constraint attribute values (which are remapped to the target language's values)
is copied verbatim: line count, syllable counts, rhyme scheme, custom code.

This module is the single conversion implementation: the frontend's "apply
conversion", the template-editing AI's ``set_from_template`` tool, and any later
caller all go through :func:`convert_template` for the same result, avoiding
duplicated conversion logic.
"""

from typing import Any

from . import custom_template_schemes
from . import get as get_template
from .rhyme import normalize_rhyme_scheme
from .structural import normalize_structural_rules

#: Chinese aliases for constraint attribute values (AI/users may describe
#: heavy/light or long/short in Chinese).
_VALUE_ALIASES: dict[str, str] = {
    "重": "heavy",
    "轻": "light",
    "长": "long",
    "短": "short",
    "平": "平",
    "仄": "仄",
}

#: Maximum line count of a custom template.
_MAX_LINES = 30

#: Allowed syllable count range per line of a custom template.
_MIN_SYLLABLES = 1
_MAX_SYLLABLES = 100


def constraint_scheme(language: str) -> tuple[str, tuple[str, ...]]:
    """Return the per-position constraint scheme of a language.

    Args:
        language: Language code.

    Returns:
        (Attribute dimension key, allowed values tuple); unknown languages are
        treated as having no attribute.

    """
    return custom_template_schemes().get(language, ("", ()))


def normalize_constraint_value(language: str, value: Any) -> str | None:
    """Normalize a constraint value to the canonical value of its language.

    Args:
        language: Language code.
        value: Raw value (may be a Chinese alias).

    Returns:
        Canonical value or empty string; None for invalid values.

    """
    attribute, values = constraint_scheme(language)
    if not attribute:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    canonical = _VALUE_ALIASES.get(text, text)
    return canonical if canonical in values else None


def convert_syllable_count(value: Any) -> int:
    """Convert a template syllable count (fixed or range) to a fixed integer.

    Custom templates only support a fixed syllable count per line, so a range
    (such as 8-10) is reduced to its rounded midpoint.

    Args:
        value: int or a (min, max) range.

    Returns:
        Positive integer; 7 when it cannot be parsed.

    """
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            return max(1, round((int(value[0]) + int(value[1])) / 2))
        except TypeError, ValueError:
            return 7
    try:
        return max(1, int(value))
    except TypeError, ValueError:
        return 7


def _normalize_syllables(source_dict: dict[str, Any], lines: int) -> list[int]:
    """Read and normalize the syllables-per-line list of the source template.

    Args:
        source_dict: Source template ``to_dict()`` result.
        lines: Line count.

    Returns:
        List of syllable counts with length ``lines``.

    """
    raw = list(source_dict.get("syllables_per_line", []) or [])
    syllables: list[int] = []
    for item in raw[:lines]:
        count = convert_syllable_count(item)
        syllables.append(max(_MIN_SYLLABLES, min(count, _MAX_SYLLABLES)))
    while len(syllables) < lines:
        syllables.append(syllables[-1] if syllables else 7)
    return syllables


def _source_tables(
    source_dict: dict[str, Any], lines: int, syllables: list[int]
) -> list[list[list[dict[str, Any]]]]:
    """Read the source template's per-position constraints into "multiple tables".

    Args:
        source_dict: Source template ``to_dict()`` result.
        lines: Line count.
        syllables: Syllables per line.

    Returns:
        One "line -> cell" table per constraint set; one empty table when there
        are no constraints.

    """
    raw_alternatives = source_dict.get("syllable_constraint_alternatives")
    tables: list[list[Any]]
    if raw_alternatives:
        tables = [list(table or []) for table in raw_alternatives]
    elif source_dict.get("syllable_constraints"):
        tables = [list(source_dict["syllable_constraints"])]
    else:
        tables = [[]]
    normalized: list[list[list[dict[str, Any]]]] = []
    for table in tables:
        rows: list[list[dict[str, Any]]] = []
        for i in range(lines):
            raw_row = table[i] if i < len(table) and isinstance(table[i], list) else []
            cells: list[dict[str, Any]] = []
            for j in range(syllables[i]):
                cell = raw_row[j] if j < len(raw_row) else {}
                cells.append(cell if isinstance(cell, dict) else {})
            rows.append(cells)
        normalized.append(rows)
    return normalized


def _normalize_mapping(
    mapping: Any, source_language: str, target_language: str
) -> tuple[dict[str, str], str | None]:
    """Validate and normalize the "source value -> target value" mapping.

    Args:
        mapping: Raw mapping (may be None or of an invalid type).
        source_language: Source language code.
        target_language: Target language code.

    Returns:
        (Normalized mapping, error message); error is None when valid.
        Many-to-one is allowed (different source values may map to the same
        target value), but one source value can only have one target value
        (the mapping is itself a function).

    """
    result: dict[str, str] = {}
    if mapping is None:
        return result, None
    if not isinstance(mapping, dict):
        return {}, "mapping must be an object"
    for source, target in mapping.items():
        source_value = normalize_constraint_value(source_language, source)
        target_value = normalize_constraint_value(target_language, target)
        if source_value is None:
            return {}, f"Invalid source attribute value {source!r}"
        if target_value is None:
            return {}, f"Invalid target attribute value {target!r}"
        if source_value:
            result[source_value] = target_value
    return result, None


def _convert_cell(
    cell: dict[str, Any],
    source_attribute: str,
    target_attribute: str,
    target_values: tuple[str, ...],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Convert one constraint cell of the source language to the target language.

    Args:
        cell: Source cell ({onset, nucleus, coda, attributes}).
        source_attribute: Source attribute dimension key ("" means no attribute).
        target_attribute: Target attribute dimension key ("" means no attribute).
        target_values: Allowed attribute values of the target language.
        mapping: Normalized attribute-value mapping.

    Returns:
        Constraint cell in the target language; onset/nucleus/coda are not
        carried across languages and are always cleared.

    """
    attributes = cell.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    source_value = (
        str(attributes.get(source_attribute, "") or "") if source_attribute else ""
    )
    mapped = mapping.get(source_value, "") if target_attribute else ""
    if mapped not in target_values:
        mapped = ""
    target_attributes = {"tone": "", "stress": "", "length": ""}
    if target_attribute and mapped:
        target_attributes[target_attribute] = mapped
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": target_attributes,
    }


def _convert_structural_rules(
    source_dict: dict[str, Any],
    target_language: str,
    mapping: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Convert the source template's data-driven structural rules to the target.

    Only attribute/level_value/oblique_value are replaced (with the mapped
    target-language attribute and values); all other fields (fixed positions,
    rhyme lines, three-level-tail/isolated-level switches) are copied verbatim.

    Args:
        source_dict: Source template ``to_dict()`` result.
        target_language: Target language code.
        mapping: Normalized attribute-value mapping.

    Returns:
        (Normalized structural rules or None, reason when not carried); both
        may be None at the same time.

    """
    rules, error = normalize_structural_rules(source_dict.get("structural_rules"))
    if error:
        return None, f"Source template structural rules are invalid ({error})"
    if rules is None:
        return None, None
    target_attribute, target_values = constraint_scheme(target_language)
    if not target_attribute:
        return None, (
            "Regulated-verse structural rules not carried: "
            "the target language has no matching syllable attribute"
        )
    level = mapping.get(str(rules["level_value"]), "")
    oblique = mapping.get(str(rules["oblique_value"]), "")
    if (
        not level
        or not oblique
        or level not in target_values
        or oblique not in target_values
    ):
        return None, (
            "Regulated-verse structural rules not carried: "
            "the mapping does not cover the target values for level/oblique"
        )
    if level == oblique:
        return None, (
            "Regulated-verse structural rules not carried: "
            "the mapping sends level and oblique to the same target value"
        )
    converted = dict(rules)
    converted["attribute"] = target_attribute
    converted["level_value"] = level
    converted["oblique_value"] = oblique
    converted["positions"] = list(rules["positions"])
    converted["rhyme_lines"] = list(rules["rhyme_lines"])
    return converted, None


def _carried_rule_codes(
    alternatives: list[list[list[dict[str, Any]]]],
    rhyme_scheme: str,
    code: str,
    structural_rules: dict[str, Any] | None,
    rule_note: str,
) -> list[str]:
    """Build the list of rule codes carried by the conversion (for UI/AI display).

    Args:
        alternatives: Converted constraint tables.
        rhyme_scheme: Converted rhyme scheme.
        code: Copied custom code.
        structural_rules: Converted structural rules.
        rule_note: Copied template rule description.

    Returns:
        Rule code list (constraints/rhyme/custom_code/jinti).

    """
    carried = ["constraints"]
    if len(alternatives) > 1:
        carried.append("multiple_kinds")
    if rhyme_scheme:
        carried.append("rhyme")
    if code.strip():
        carried.append("custom_code")
    if structural_rules:
        carried.append("jinti")
    if rule_note.strip():
        carried.append("rule_note")
    return carried


def convert_template(
    base_key: str,
    target_language: str,
    mapping: Any = None,
) -> tuple[dict[str, Any], str | None]:
    """Convert a template's full spec into a new template spec in a target language.

    Line count, syllables per line, constraint kind count, rhyme scheme, and
    custom code are copied verbatim; the constraint attribute values are
    converted from the source language's values to the target language's values
    according to ``mapping`` (the only content the conversion must rewrite).

    Args:
        base_key: Source template key.
        target_language: Target language code (zh/en/fr/it/la).
        mapping: Mapping from source attribute values to target attribute values.

    Returns:
        (Converted template spec, error message); on success the spec contains
        status="ok", lines, syllables_per_line, constraints, alternatives,
        rhyme_scheme, rhyme_distinct, code, source_name, source_language, and
        mapped.

    """
    if target_language not in custom_template_schemes():
        return {}, "Unsupported target language"
    try:
        source = get_template(base_key)
    except KeyError:
        return {}, f"Unknown template key: {base_key!r}"
    source_dict = source.to_dict()
    source_language = str(source_dict.get("language", ""))
    source_attribute, _source_values = constraint_scheme(source_language)
    target_attribute, target_values = constraint_scheme(target_language)

    normalized_mapping, mapping_error = _normalize_mapping(
        mapping, source_language, target_language
    )
    if mapping_error:
        return {}, mapping_error

    try:
        raw_lines = int(source_dict.get("lines", 4))
    except TypeError, ValueError:
        raw_lines = 4
    lines = max(1, min(raw_lines, _MAX_LINES))
    syllables = _normalize_syllables(source_dict, lines)
    source_tables = _source_tables(source_dict, lines, syllables)
    alternatives: list[list[list[dict[str, Any]]]] = []
    for table in source_tables:
        alternatives.append(
            [
                [
                    _convert_cell(
                        cell,
                        source_attribute,
                        target_attribute,
                        target_values,
                        normalized_mapping,
                    )
                    for cell in row
                ]
                for row in table
            ]
        )

    raw_scheme = str(source_dict.get("rhyme_scheme", "") or "")
    rhyme_scheme, scheme_error = normalize_rhyme_scheme(raw_scheme, lines)
    if scheme_error:
        # A source rhyme scheme that does not match the line count cannot be
        # carried, so it is treated as "no rhyme scheme".
        rhyme_scheme = ""
    rhyme_distinct = bool(source_dict.get("rhyme_distinct", False))
    if not rhyme_scheme:
        rhyme_distinct = False

    structural_rules, structural_drop_reason = _convert_structural_rules(
        source_dict, target_language, normalized_mapping
    )
    custom_code = str(source_dict.get("custom_code", "") or "")
    # Reuse the source template's rule description after conversion: prefer the
    # user-provided rule_note, otherwise the built-in/auto-generated
    # rule_description; the user can keep editing it in the UI.
    rule_note = str(source_dict.get("rule_note", "") or "").strip()
    if not rule_note:
        rule_note = str(source_dict.get("rule_description", "") or "").strip()
    carried_rules = _carried_rule_codes(
        alternatives, rhyme_scheme, custom_code, structural_rules, rule_note
    )
    dropped_rules = [str(rule) for rule in (source_dict.get("special_rules") or [])]
    if structural_drop_reason:
        dropped_rules.insert(0, structural_drop_reason)

    spec: dict[str, Any] = {
        "status": "ok",
        "source_template_key": base_key,
        "source_name": str(source_dict.get("name", "")),
        "source_language": source_language,
        "language": target_language,
        "lines": lines,
        "syllables_per_line": syllables,
        "constraints": alternatives[0],
        "alternatives": alternatives,
        "rhyme_scheme": rhyme_scheme,
        "rhyme_distinct": rhyme_distinct,
        "code": custom_code,
        "rule_note": rule_note,
        "structural_rules": structural_rules,
        "carried_rules": carried_rules,
        "dropped_rules": dropped_rules,
        "mapped": normalized_mapping,
    }
    return spec, None


def constraint_tables_to_values(
    tables: list[list[list[dict[str, Any]]]], language: str
) -> list[list[list[str]]]:
    """Convert constraint dict tables to "canonical value string tables" for UI/AI drafts.

    Args:
        tables: Multiple constraint tables (line -> cell -> {attributes}).
        language: Language code.

    Returns:
        Multiple value tables: constraint kind -> line -> canonical value per
        syllable ("" means free).

    """
    attribute, _values = constraint_scheme(language)
    result: list[list[list[str]]] = []
    for table in tables:
        rows: list[list[str]] = []
        for row in table:
            values: list[str] = []
            for cell in row:
                attributes = (
                    cell.get("attributes", {}) if isinstance(cell, dict) else {}
                )
                if not isinstance(attributes, dict):
                    attributes = {}
                value = str(attributes.get(attribute, "") or "") if attribute else ""
                values.append(value)
            rows.append(values)
        result.append(rows)
    return result
