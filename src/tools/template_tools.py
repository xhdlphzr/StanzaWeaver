# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Tool definitions and execution for the template-editing AI.

The template-editing AI configures custom templates through these tools, one to
one with what users can configure in the UI: template info (name, language,
line count), syllables per line, constraint kind count, positional syllable
constraints, rhyme scheme, and custom validation code. The AI only edits the
in-memory draft; ``submit_template`` finally persists it server-side and
registers the template.
"""

from dataclasses import dataclass, field
from typing import Any

from ..templates import ConstraintTable
from ..templates.convert import (
    constraint_scheme,
    constraint_tables_to_values,
    convert_template,
    normalize_constraint_value,
)

#: Maximum number of constraint kinds.
MAX_CONSTRAINT_KINDS = 8

#: Maximum number of template lines.
MAX_TEMPLATE_LINES = 30

#: Supported languages.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("zh", "en", "it", "fr", "la")

SET_TEMPLATE_INFO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_template_info",
        "description": (
            "Set the basic template info: name, language, lines. The language "
            "determines the per-syllable attributes available: zh uses 平/仄; "
            "en/it use light/heavy; la uses long/short; fr has no per-syllable "
            "attribute. Changing the line count automatically adjusts the "
            "syllables per line and the constraint tables."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": 'Template name, e.g. "浣溪沙"',
                },
                "language": {
                    "type": "string",
                    "enum": list(SUPPORTED_LANGUAGES),
                    "description": "Language code",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines (1-30)",
                },
            },
            "required": [],
        },
    },
}

SET_SYLLABLES_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_syllables_per_line",
        "description": (
            "Set syllables per line. The array length must equal the template "
            "line count; the constraint tables adjust automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "syllables": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Syllables per line, e.g. [7,7,7,7]",
                },
            },
            "required": ["syllables"],
        },
    },
}

SET_KIND_COUNT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_constraint_kind_count",
        "description": (
            "Set the number of constraint kinds (1-8). Kinds are alternatives "
            "(OR): the AI only needs to satisfy any one of them, e.g. the four "
            "tone patterns of a quatrain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of constraint kinds (1-8)",
                },
            },
            "required": ["count"],
        },
    },
}

SET_CONSTRAINTS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_syllable_constraints",
        "description": (
            "Fill in the positional syllable constraints for one constraint "
            "kind. constraints is a 2-D array: one entry per line in the outer "
            "array, one entry per syllable in the inner array; each value is a "
            "canonical attribute value for the language or an empty string "
            "(empty = that position is free). Canonical values: zh uses 平/仄; "
            "en/it use light/heavy; la uses long/short; fr accepts only empty "
            "strings. The Chinese aliases 重/轻/长/短 are also accepted."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "alternative": {
                    "type": "integer",
                    "description": "Which constraint kind (0-based, default 0)",
                },
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": (
                        "Constraint values line by line and syllable by "
                        "syllable, e.g. [[平,仄,平,仄,平], ...]"
                    ),
                },
            },
            "required": ["constraints"],
        },
    },
}

SET_FROM_TEMPLATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_from_template",
        "description": (
            "Convert from an existing template (in any language): line count, "
            "syllables per line, constraint kinds, rhyme scheme, and custom "
            "code are copied as-is; only the source-language attribute values "
            "of positional constraints are mapped to target-language attribute "
            "values through mapping, e.g. "
            '{"平": "heavy", "仄": "light"}. Multiple source values may map to '
            "the same target value (many-to-one), but each source value may "
            "have only one target value. Unlisted source values are treated as "
            "free."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_key": {
                    "type": "string",
                    "description": "Source template key, e.g. zh_wujue / en_sonnet",
                },
                "mapping": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": ("Mapping from source to target attribute values"),
                },
            },
            "required": ["template_key"],
        },
    },
}

SET_RHYME_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_rhyme_scheme",
        "description": (
            "Set the rhyme scheme, e.g. a Shakespearean sonnet is "
            "ABAB CDCD EFEF GG; lines with the same letter must rhyme, '-' "
            "means the line does not rhyme, and lines that must not rhyme use "
            "'-'. When distinct=true, different rhyme groups must differ from "
            "each other (e.g. a sonnet's A and B rhymes differ). Pass an empty "
            "string to clear the rhyme rule."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scheme": {
                    "type": "string",
                    "description": "Rhyme scheme string, e.g. ABAB CDCD EFEF GG",
                },
                "distinct": {
                    "type": "boolean",
                    "description": (
                        "Whether different rhyme groups must differ; default false"
                    ),
                },
            },
            "required": ["scheme"],
        },
    },
}

SET_RULE_DESCRIPTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_rule_description",
        "description": (
            "Set the template rule description. This text is provided as a "
            "prompt to the writing AI that generates poems, describing "
            "natural-language rules beyond positional constraints and rhyme "
            "scheme (genre, sentence pattern, parallelism, imagery structure, "
            "etc.). Pass an empty string to clear it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "Template rule description provided to the writing AI"
                    ),
                },
            },
            "required": ["description"],
        },
    },
}

SET_CODE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_custom_code",
        "description": (
            "Set custom whole-poem validation code (Python; it is written into "
            "the generated template's validate_full and runs after the "
            "positional-constraint and rhyme checks; use errors.append(...) to "
            "append errors, and reuse the language's helper functions via "
            "rules.<function name>). Pass an empty string to clear it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code (do not include a def validate_full definition)"
                    ),
                },
            },
            "required": ["code"],
        },
    },
}

GET_DRAFT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_template_draft",
        "description": (
            "Read the full current template draft (name/language/lines/"
            "constraint tables/rhyme scheme/code)."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

SUBMIT_TEMPLATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_template",
        "description": (
            "Submit the template: the server validates it, generates the "
            "template file, and registers the template. Call it only after the "
            "template name, language, lines, and constraints are all set."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

TEMPLATE_TOOLS: list[dict[str, Any]] = [
    SET_TEMPLATE_INFO_TOOL,
    SET_SYLLABLES_TOOL,
    SET_KIND_COUNT_TOOL,
    SET_CONSTRAINTS_TOOL,
    SET_FROM_TEMPLATE_TOOL,
    SET_RHYME_TOOL,
    SET_RULE_DESCRIPTION_TOOL,
    SET_CODE_TOOL,
    GET_DRAFT_TOOL,
    SUBMIT_TEMPLATE_TOOL,
]


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Clamp an arbitrary value to an integer within a range.

    Args:
        value: Raw value.
        default: Default when conversion fails.
        minimum: Lower bound.
        maximum: Upper bound.

    Returns:
        Integer within the range.

    """
    try:
        number = int(value)
    except TypeError, ValueError:
        number = default
    return max(minimum, min(number, maximum))


@dataclass
class TemplateDraft:
    """Mutable draft of the template-editing AI (configured in memory step by step)."""

    name: str = ""
    language: str = "zh"
    lines: int = 4
    syllables_per_line: list[int] = field(default_factory=lambda: [7, 7, 7, 7])
    #: Constraint kind -> line -> per-syllable canonical value ("" means free).
    alternatives: list[list[list[str]]] = field(
        default_factory=lambda: [[[""] * 7 for _ in range(4)]]
    )
    rhyme_scheme: str = ""
    rhyme_distinct: bool = False
    code: str = ""
    #: Materialized structural rules (e.g. regulated-verse tone skeleton,
    #: three-level ending, solitary level); copied along with conversions.
    structural_rules: dict[str, Any] | None = None
    #: User-provided template rule description (passed to the writing AI as a
    #: prompt).
    rule_note: str = ""
    submitted: bool = False

    def normalize(self) -> None:
        """Normalize draft fields and fill in missing constraint cells."""
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "zh"
        self.lines = _clamp_int(self.lines, 4, 1, MAX_TEMPLATE_LINES)
        syllables: list[int] = []
        for item in self.syllables_per_line[: self.lines]:
            syllables.append(_clamp_int(item, 7, 1, 100))
        while len(syllables) < self.lines:
            syllables.append(syllables[-1] if syllables else 7)
        self.syllables_per_line = syllables

        from ..templates.structural import normalize_structural_rules

        rules, rules_error = normalize_structural_rules(self.structural_rules)
        self.structural_rules = None if rules_error else rules
        self.rule_note = str(self.rule_note or "")[:4000]

        if not self.alternatives:
            self.alternatives = [[[""] * count for count in syllables]]
        alternatives: list[list[list[str]]] = []
        for alternative in self.alternatives[:MAX_CONSTRAINT_KINDS]:
            table: list[list[str]] = []
            for i in range(self.lines):
                line = list(alternative[i]) if i < len(alternative) else []
                values: list[str] = []
                for j in range(syllables[i]):
                    raw = line[j] if j < len(line) else ""
                    normalized = normalize_constraint_value(self.language, raw)
                    values.append(normalized if normalized is not None else "")
                table.append(values)
            alternatives.append(table)
        self.alternatives = alternatives

    def to_payload(self) -> dict[str, Any]:
        """Serialize to a draft dictionary consumable by the frontend.

        Returns:
            {name, language, lines, syllables_per_line, alternatives,
             rhyme_scheme, rhyme_distinct, code}.

        """
        return {
            "name": self.name,
            "language": self.language,
            "lines": self.lines,
            "syllables_per_line": list(self.syllables_per_line),
            "alternatives": [
                [list(line) for line in table] for table in self.alternatives
            ],
            "rhyme_scheme": self.rhyme_scheme,
            "rhyme_distinct": self.rhyme_distinct,
            "code": self.code,
            "structural_rules": (
                dict(self.structural_rules) if self.structural_rules else None
            ),
            "rule_note": self.rule_note,
        }

    def constraint_tables(self) -> list[ConstraintTable]:
        """Convert value tables into template constraint dictionaries.

        The result is used to generate the template source code.

        Returns:
            One ConstraintTable per constraint kind.

        """
        attribute, _values = constraint_scheme(self.language)
        tables: list[ConstraintTable] = []
        for alternative in self.alternatives:
            table: ConstraintTable = []
            for line in alternative:
                cells: list[dict[str, Any]] = []
                for value in line:
                    attributes = {"tone": "", "stress": "", "length": ""}
                    if attribute and value:
                        attributes[attribute] = value
                    cells.append(
                        {
                            "onset": "",
                            "nucleus": "",
                            "coda": "",
                            "attributes": attributes,
                        }
                    )
                table.append(cells)
            tables.append(table)
        return tables


def draft_from_payload(payload: dict[str, Any]) -> TemplateDraft:
    """Build and normalize a TemplateDraft from the frontend payload.

    Args:
        payload: Frontend draft (invalid fields fall back to defaults).

    Returns:
        The normalized TemplateDraft.

    """
    draft = TemplateDraft()
    draft.name = str(payload.get("name", "")).strip()
    draft.language = str(payload.get("language", "zh"))
    draft.code = str(payload.get("code", ""))
    draft.rhyme_scheme = str(payload.get("rhyme_scheme", "")).strip()
    draft.rhyme_distinct = bool(payload.get("rhyme_distinct", False))
    try:
        draft.lines = int(payload.get("lines", 4))
    except TypeError, ValueError:
        draft.lines = 4
    raw_syllables = payload.get("syllables_per_line")
    if isinstance(raw_syllables, list) and raw_syllables:
        draft.syllables_per_line = list(raw_syllables)
    draft.rule_note = str(payload.get("rule_note", "") or "")
    raw_rules = payload.get("structural_rules")
    if isinstance(raw_rules, dict):
        draft.structural_rules = raw_rules
    raw_alternatives = payload.get("alternatives")
    alternatives: list[list[list[str]]] = []
    if isinstance(raw_alternatives, list):
        for alternative in raw_alternatives:
            if not isinstance(alternative, list):
                continue
            table: list[list[str]] = []
            for line in alternative:
                if isinstance(line, list):
                    table.append([str(cell) for cell in line])
                else:
                    table.append([])
            alternatives.append(table)
    if alternatives:
        draft.alternatives = alternatives
    draft.normalize()
    return draft


def _draft_summary(draft: TemplateDraft) -> dict[str, Any]:
    """Return a short summary of the draft (used in tool results).

    Args:
        draft: Template draft.

    Returns:
        Short summary dictionary.

    """
    return {
        "name": draft.name,
        "language": draft.language,
        "lines": draft.lines,
        "syllables_per_line": list(draft.syllables_per_line),
        "constraint_kinds": len(draft.alternatives),
        "rhyme_scheme": draft.rhyme_scheme,
        "rhyme_distinct": draft.rhyme_distinct,
        "has_custom_code": bool(draft.code.strip()),
        "has_structural_rules": draft.structural_rules is not None,
        "has_rule_note": bool(draft.rule_note.strip()),
    }


def execute_set_template_info(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_template_info.

    Args:
        draft: Template draft.
        arguments: Tool arguments (name/language/lines).

    Returns:
        ok or error result dictionary.

    """
    if "name" in arguments:
        name = str(arguments.get("name", "")).strip()
        if not name:
            return {"error": "Template name cannot be empty"}
        draft.name = name
    if "language" in arguments:
        language = str(arguments.get("language", "")).strip()
        if language not in SUPPORTED_LANGUAGES:
            return {"error": f"Unsupported language {language!r}"}
        draft.language = language
    if "lines" in arguments:
        draft.lines = _clamp_int(arguments.get("lines"), draft.lines, 1, 30)
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_syllables(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_syllables_per_line.

    Args:
        draft: Template draft.
        arguments: Tool arguments (syllables).

    Returns:
        ok or error result dictionary.

    """
    raw = arguments.get("syllables")
    if not isinstance(raw, list):
        return {"error": "syllables must be an integer array"}
    if len(raw) != draft.lines:
        return {"error": f"syllables length must be {draft.lines}, got {len(raw)}"}
    syllables: list[int] = []
    for item in raw:
        try:
            syllables.append(int(item))
        except TypeError, ValueError:
            return {"error": "syllables must all be integers"}
    if any(value < 1 for value in syllables):
        return {"error": "Syllables per line must be positive integers"}
    draft.syllables_per_line = syllables
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_kind_count(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_constraint_kind_count.

    Args:
        draft: Template draft.
        arguments: Tool arguments (count).

    Returns:
        ok or error result dictionary.

    """
    try:
        count = int(arguments.get("count", 1))
    except TypeError, ValueError:
        return {"error": "count must be an integer"}
    if count < 1 or count > MAX_CONSTRAINT_KINDS:
        return {
            "error": (
                f"Constraint kind count must be between 1 and {MAX_CONSTRAINT_KINDS}"
            )
        }
    draft.normalize()
    while len(draft.alternatives) < count:
        draft.alternatives.append([[""] * n for n in draft.syllables_per_line])
    draft.alternatives = draft.alternatives[:count]
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_constraints(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_syllable_constraints.

    Args:
        draft: Template draft.
        arguments: Tool arguments (alternative/constraints).

    Returns:
        ok or error result dictionary.

    """
    raw = arguments.get("constraints")
    if not isinstance(raw, list):
        return {"error": "constraints must be a 2-D array"}
    draft.normalize()
    try:
        alternative_index = int(arguments.get("alternative", 0))
    except TypeError, ValueError:
        return {"error": "alternative must be an integer"}
    if alternative_index < 0 or alternative_index >= len(draft.alternatives):
        return {
            "error": (
                f"alternative is out of range: there are "
                f"{len(draft.alternatives)} constraint kinds"
            )
        }
    table: list[list[str]] = []
    for i in range(len(draft.alternatives[alternative_index])):
        row = raw[i] if i < len(raw) else []
        if not isinstance(row, list):
            row = []
        values: list[str] = []
        for j in range(draft.syllables_per_line[i]):
            cell = row[j] if j < len(row) else ""
            normalized = normalize_constraint_value(draft.language, cell)
            if normalized is None:
                return {
                    "error": (
                        f"Invalid constraint value {cell!r} at line {i + 1}, "
                        f"position {j + 1}"
                    )
                }
            values.append(normalized)
        table.append(values)
    draft.alternatives[alternative_index] = table
    draft.normalize()
    return {
        "status": "ok",
        "alternative": alternative_index,
        "cells": sum(len(row) for row in table),
    }


def execute_set_from_template(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_from_template (unified cross-language template conversion).

    The conversion is done by
    :func:`src.templates.convert.convert_template`: line count, syllable
    count, constraint kinds, rhyme scheme, and custom code are copied as-is;
    only the attribute values of positional constraints are converted through
    the mapping.

    Args:
        draft: Template draft (modified in place).
        arguments: Tool arguments (template_key / mapping).

    Returns:
        ok or error result dictionary.

    """
    key = str(arguments.get("template_key", "")).strip()
    if not key:
        return {"error": "template_key cannot be empty"}
    spec, error = convert_template(key, draft.language, arguments.get("mapping"))
    if error:
        return {"error": error}
    draft.lines = int(spec["lines"])
    draft.syllables_per_line = list(spec["syllables_per_line"])
    draft.alternatives = constraint_tables_to_values(
        list(spec["alternatives"]), draft.language
    )
    draft.rhyme_scheme = str(spec["rhyme_scheme"])
    draft.rhyme_distinct = bool(spec["rhyme_distinct"])
    draft.code = str(spec["code"])
    raw_rules = spec.get("structural_rules")
    draft.structural_rules = raw_rules if isinstance(raw_rules, dict) else None
    draft.rule_note = str(spec.get("rule_note", "") or "")
    draft.normalize()
    if not draft.name:
        draft.name = f"{spec['source_name']}-{draft.language}"
    return {
        "status": "ok",
        "template_key": key,
        "source_language": spec["source_language"],
        "mapped": spec["mapped"],
        "rhyme_scheme": draft.rhyme_scheme,
        "has_custom_code": bool(draft.code.strip()),
        "carried_rules": list(spec.get("carried_rules") or []),
        "dropped_rules": list(spec.get("dropped_rules") or []),
        **_draft_summary(draft),
    }


def execute_set_rhyme(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_rhyme_scheme.

    Args:
        draft: Template draft.
        arguments: Tool arguments (scheme/distinct).

    Returns:
        ok or error result dictionary.

    """
    from ..templates.rhyme import normalize_rhyme_scheme

    scheme = str(arguments.get("scheme", ""))
    cleaned, error = normalize_rhyme_scheme(scheme, draft.lines)
    if error:
        return {"error": error}
    draft.rhyme_scheme = cleaned
    if "distinct" in arguments:
        draft.rhyme_distinct = bool(arguments.get("distinct"))
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_rule_description(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_rule_description (template rule description for the writing AI).

    Args:
        draft: Template draft.
        arguments: Tool arguments (description).

    Returns:
        ok result dictionary.

    """
    draft.rule_note = str(arguments.get("description", "") or "").strip()[:4000]
    return {"status": "ok", "has_rule_note": bool(draft.rule_note)}


def execute_set_code(draft: TemplateDraft, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute set_custom_code.

    Args:
        draft: Template draft.
        arguments: Tool arguments (code).

    Returns:
        ok result dictionary.

    """
    draft.code = str(arguments.get("code", "")).replace("\r\n", "\n")
    return {"status": "ok", "has_custom_code": bool(draft.code.strip())}


def execute_template_tool(
    draft: TemplateDraft, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute one template-editing operation by tool name.

    Args:
        draft: Template draft (modified in place).
        name: Tool name.
        arguments: Tool arguments.

    Returns:
        Tool execution result dictionary.

    """
    if name == "set_template_info":
        return execute_set_template_info(draft, arguments)
    if name == "set_syllables_per_line":
        return execute_set_syllables(draft, arguments)
    if name == "set_constraint_kind_count":
        return execute_set_kind_count(draft, arguments)
    if name == "set_syllable_constraints":
        return execute_set_constraints(draft, arguments)
    if name == "set_from_template":
        return execute_set_from_template(draft, arguments)
    if name == "set_rhyme_scheme":
        return execute_set_rhyme(draft, arguments)
    if name == "set_rule_description":
        return execute_set_rule_description(draft, arguments)
    if name == "set_custom_code":
        return execute_set_code(draft, arguments)
    if name == "get_template_draft":
        return {"status": "ok", "draft": draft.to_payload()}
    if name == "submit_template":
        if not draft.name:
            return {"error": "Set the template name with set_template_info first"}
        draft.normalize()
        draft.submitted = True
        return {
            "status": "submitted",
            "message": "Template submitted; the server will create and register it",
        }
    return {"error": f"Unknown template tool {name}"}
