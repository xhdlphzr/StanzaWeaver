# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Metrical template base class and registry.

A template (``PoetryTemplate``) defines all metrical rules of a poetic form:
- syllables_per_line: syllables per line (int or a (min, max) range);
- get_syllable_constraints(): per-position constraints (for single-line modify
  validation and LLM prompts);
- validate_full(): full rule checking (cross-line rules such as rhyme and
  three-level-tail);
- describe(): human-readable metrical description for the LLM.
"""

import re
from abc import ABC
from collections.abc import Sequence
from typing import Any, ClassVar

from ..models.syllable import Syllable

SyllableCount = int | tuple[int, int]
ConstraintDict = dict[str, Any]
ConstraintLine = list[ConstraintDict]
ConstraintTable = list[ConstraintLine]


def _make_syl(**kwargs: Any) -> dict[str, Any]:
    """Build a per-position constraint dict.

    Args:
        **kwargs: May contain onset/nucleus/coda and an attributes sub-dict.

    Returns:
        Constraint dict (with all three attributes keys).

    """
    attrs = kwargs.pop("attributes", {})
    if not isinstance(attrs, dict):
        attrs = {}
    return {
        "onset": kwargs.get("onset", ""),
        "nucleus": kwargs.get("nucleus", ""),
        "coda": kwargs.get("coda", ""),
        "attributes": {
            "tone": attrs.get("tone", ""),
            "stress": attrs.get("stress", ""),
            "length": attrs.get("length", ""),
        },
    }


def _last_word(line: str, allowed_chars: str) -> str:
    """Get the last word of a line (punctuation stripped, lowercased).

    Args:
        line: One line of poetry.
        allowed_chars: Characters allowed in the regex character class
            (without brackets).

    Returns:
        Last word of the line; empty string for an empty line.

    """
    if not line.strip():
        return ""
    return re.sub(rf"[^{allowed_chars}]", "", line.strip().split()[-1]).lower()


def _describe_constraint_table(
    lines_spec: Sequence[SyllableCount], constraints: ConstraintTable
) -> str:
    """Render one per-position constraint table as a multi-line description.

    Args:
        lines_spec: Syllable count per line.
        constraints: Per-position constraint table.

    Returns:
        Multi-line description text.

    """
    lines_desc = ""
    for i, cnt in enumerate(lines_spec):
        line_constraints = constraints[i] if i < len(constraints) else []
        line_info = f"  Line {i + 1}: {format_count(cnt)} syllables"
        if line_constraints:
            parts = []
            for j, c in enumerate(line_constraints):
                desc_parts = []
                if c.get("onset"):
                    desc_parts.append(f"onset={c['onset']}")
                if c.get("nucleus"):
                    desc_parts.append(f"nucleus={c['nucleus']}")
                if c.get("coda"):
                    desc_parts.append(f"coda={c['coda']}")
                for k, v in c.get("attributes", {}).items():
                    if v:
                        desc_parts.append(f"{k}={v}")
                if desc_parts:
                    parts.append(f"    position {j + 1}: {','.join(desc_parts)}")
            if parts:
                line_info += "\n" + "\n".join(parts)
        lines_desc += "\n" + line_info
    return lines_desc


def describe_template_from_dict(template_dict: dict[str, Any]) -> str:
    """Build a metrical description from a template dict (fallback without an object).

    Args:
        template_dict: Dict containing lines/syllables_per_line/
            syllable_constraints and optional syllable_constraint_alternatives.

    Returns:
        Multi-line metrical description text.

    """
    lines_spec = template_dict.get("syllables_per_line", [])
    lines_desc = f"{template_dict.get('lines', len(lines_spec))} lines in total"
    alternatives = template_dict.get("syllable_constraint_alternatives") or []
    if alternatives:
        lines_desc += (
            f" ({len(alternatives)} syllable constraint variants; any one suffices)"
        )
        for k, table in enumerate(alternatives, start=1):
            lines_desc += f"\n[Constraint variant {k}]"
            lines_desc += _describe_constraint_table(lines_spec, list(table or []))
        return lines_desc
    constraints = template_dict.get("syllable_constraints") or []
    return lines_desc + _describe_constraint_table(lines_spec, list(constraints))


def _copy_structural_rules(
    rules: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Copy a structural-rules dict (list fields are shallow-copied).

    This prevents callers from accidentally mutating template constants.

    Args:
        rules: Structural-rules dict or None.

    Returns:
        Copied dict, or None.

    """
    if not rules:
        return None
    copied = dict(rules)
    for key in ("positions", "rhyme_lines"):
        value = copied.get(key)
        if isinstance(value, (list, tuple)):
            copied[key] = list(value)
    return copied


class PoetryTemplate(ABC):
    """Metrical template base class (one subclass per poetic form)."""

    name: ClassVar[str] = ""
    language: ClassVar[str] = ""
    lines: ClassVar[int] = 0
    # Sequence (covariant) lets subclasses override with list[int] or
    # list[tuple[int, int]].
    syllables_per_line: ClassVar[Sequence[SyllableCount]] = []
    rule_description: ClassVar[str] = ""
    #: Rhyme scheme (e.g. "ABAB CDCD EFEF GG"; empty means the template has no
    #: explicit convertible scheme).
    rhyme_scheme: ClassVar[str] = ""
    #: Whether different rhyme groups must be distinct.
    rhyme_distinct: ClassVar[bool] = False
    #: User-defined whole-poem validation code (for custom templates; empty for
    #: built-in templates).
    custom_code: ClassVar[str] = ""
    #: User-entered template rule description (passed as prompt to the writing AI).
    rule_note: ClassVar[str] = ""
    #: Data-driven structural rules (e.g. the regulated-verse tone skeleton,
    #: three-level tail, isolated level), copied during cross-language conversion.
    structural_rules: ClassVar[dict[str, Any] | None] = None
    #: Language-specific rules implemented only in code and not carried by
    #: conversion (shown as frontend hints).
    special_rules: ClassVar[tuple[str, ...]] = ()
    #: Whether to center when displaying (poems are centered; long-line forms
    #: such as ci may override to False for left alignment).
    centered: ClassVar[bool] = True

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """Return the per-position syllable constraint table (one list per line).

        Returns:
            Constraint table; None when unconstrained.

        """
        return None

    def get_syllable_constraint_alternatives(self) -> list[ConstraintTable] | None:
        """Return multiple per-position constraint tables (OR relationship).

        Satisfying any one table suffices.

        Returns:
            List of constraint tables; None when multiple constraints are not configured.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Run the template-specific full rule check.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line (``analyze_line`` result).

        Returns:
            List of error messages (empty means pass).

        """
        return []

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict (for validators and the frontend).

        Returns:
            {"name", "language", "lines", "syllables_per_line",
             "syllable_constraints", "syllable_constraint_alternatives",
             "rhyme_scheme", "rhyme_distinct", "custom_code", "centered"}.

        """
        return {
            "name": self.name,
            "language": self.language,
            "lines": self.lines,
            "syllables_per_line": list(self.syllables_per_line),
            "syllable_constraints": self.get_syllable_constraints(),
            "syllable_constraint_alternatives": (
                self.get_syllable_constraint_alternatives()
            ),
            "rhyme_scheme": self.rhyme_scheme,
            "rhyme_distinct": self.rhyme_distinct,
            "custom_code": self.custom_code,
            "rule_description": self.rule_description,
            "rule_note": self.rule_note,
            "structural_rules": _copy_structural_rules(self.structural_rules),
            "special_rules": list(self.special_rules),
            "centered": self.centered,
        }

    def describe(self) -> str:
        """Build the human-readable metrical description for the AI prompt.

        Returns:
            Multi-line text: line count, syllables per line, per-position
            constraints, and natural-language rules.
            A user-entered rule description (rule_note) is appended to the
            prompt body.

        """
        lines_desc = describe_template_from_dict(
            {
                "lines": self.lines,
                "syllables_per_line": self.syllables_per_line,
                "syllable_constraints": self.get_syllable_constraints(),
                "syllable_constraint_alternatives": (
                    self.get_syllable_constraint_alternatives()
                ),
            }
        )
        if self.rule_note:
            lines_desc += "\n" + self.rule_note
        if self.rule_description:
            lines_desc += "\n" + self.rule_description
        return lines_desc

    def _punctuated_content(
        self, poem: list[str], punctuation: list[str]
    ) -> tuple[str, list[str]]:
        """Punctuate body lines one by one (the title gets no punctuation).

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Punctuation list (one entry per body line).

        Returns:
            (Title, punctuated body lines).

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marked = [
            content[i] + (punctuation[i] if i < len(punctuation) else "")
            for i in range(len(content))
        ]
        return title, marked

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Format unpunctuated poem lines into displayable text.

        Subclasses may override this for form-specific formatting (punctuation,
        indentation, stanza breaks). AI drafts come without punctuation and line
        breaks; this method adds punctuation and layout. When ``punctuation``
        is empty the form's default layout is used; when provided, it is applied
        line by line.

        Args:
            poem: Unpunctuated poem lines (first element is the title).
            punctuation: Per-line punctuation list; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        if punctuation:
            title, marked = self._punctuated_content(poem, punctuation)
            lines = "\n".join(marked)
            return title + "\n" + lines if title else lines
        return "\n".join(poem)


_registry: dict[str, PoetryTemplate] = {}


def register(key: str, template: PoetryTemplate) -> None:
    """Register a template in the global registry.

    Args:
        key: Template key (e.g. "zh_wujue").
        template: Template instance.

    """
    _registry[key] = template


def format_count(cnt: SyllableCount) -> str:
    """Format a syllable count for prompts/errors.

    Args:
        cnt: Fixed int or a (min, max) range.

    Returns:
        "5" or "15-17".

    """
    if isinstance(cnt, (tuple, list)) and len(cnt) == 2:
        return f"{cnt[0]}-{cnt[1]}"
    return str(cnt)


def get(key: str) -> PoetryTemplate:
    """Get a template by key.

    Args:
        key: Template key.

    Returns:
        Template instance.

    Raises:
        KeyError: The key is not registered.

    """
    return _registry[key]


def list_all() -> list[PoetryTemplate]:
    """Return all registered templates.

    Returns:
        List of template instances.

    """
    return list(_registry.values())


_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "汉语",
    "en": "英语",
    "it": "意大利语",
    "fr": "法语",
    "la": "古典拉丁语",
}

#: Per-position constraint schemes supported by the custom-template editor:
#: language -> (attribute dimension key, allowed values tuple).
#: The dimension key is the real field written into ``attributes``; an empty
#: dimension ("") means the language has no syllable-attribute constraints and
#: can only be limited by validate_full's whole-poem rules (rhyme/line-level
#: conditions).
_CUSTOM_SCHEMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "zh": ("tone", ("平", "仄")),
    "en": ("stress", ("light", "heavy")),
    "it": ("stress", ("light", "heavy")),
    "la": ("length", ("long", "short")),
    "fr": ("", ()),
}


def custom_template_schemes() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Return per-position constraint schemes for custom templates.

    The result also lists the supported languages.

    Returns:
        {"zh": ("tone", ("平", "仄")), ...}; keys are the supported languages,
        values are (attribute dimension key, allowed values tuple).

    """
    return dict(_CUSTOM_SCHEMES)


def template_helpers(language: str) -> tuple[str, ...]:
    """List reusable ``_check_*`` helper names in a language template module.

    Used as hints for the custom-code editor: generated templates import the
    language module under the ``rules`` alias, so custom code can reuse these
    whole-poem rule functions via ``rules.<function name>``.

    Args:
        language: Language code (zh/en/it/fr/la).

    Returns:
        Alphabetically sorted tuple of helper names; raises ModuleNotFoundError
        when the language module does not exist.

    """
    import importlib

    module = importlib.import_module(f"{__package__}.{language}")
    return tuple(sorted(name for name in dir(module) if name.startswith("_check_")))


def list_dicts() -> list[dict[str, Any]]:
    """Return all templates as dicts (with display name) for frontend dropdowns.

    Returns:
        [{"key", "name", "language", "lines", "syllables_per_line",
          "syllable_constraints", "display_name", "deletable"}, ...];
        the order is the registry's current order (user-customizable).

    """
    return [
        {
            "key": k,
            **t.to_dict(),
            "display_name": f"{t.name}（{_LANGUAGE_LABELS.get(t.language, t.language)}）",
            "deletable": k.startswith("custom_"),
        }
        for k, t in _registry.items()
    ]


def set_order(keys: Sequence[str]) -> list[str]:
    """Reorder the template registry according to the given key order.

    Args:
        keys: Desired template key order; unknown/duplicate keys are ignored,
            and registered templates not listed are appended in their original
            order.

    Returns:
        The complete reordered key list.

    """
    items = dict(_registry)
    ordered: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if isinstance(key, str) and key in items and key not in seen:
            ordered.append(key)
            seen.add(key)
    for key in items:
        if key not in seen:
            ordered.append(key)
    _registry.clear()
    for key in ordered:
        _registry[key] = items[key]
    return list(_registry)


def unregister(key: str) -> bool:
    """Remove a template from the registry (does not delete source files).

    Args:
        key: Template key.

    Returns:
        True if it existed and was removed, else False.

    """
    if key in _registry:
        del _registry[key]
        return True
    return False
