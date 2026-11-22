# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""modify tool execution: modify the draft by type (line / title / punctuation).

- line: replace a whole line (validate the new line's meter first);
- title: replace the title;
- punctuation: replace the punctuation list (its length must equal the meter
  line count).
"""

from typing import Any

from ..prosody.meter_validator import MeterValidator

#: Valid modification types.
MODIFY_TYPES: tuple[str, ...] = ("line", "title", "punctuation")


def execute_modify(
    poem: list[str],
    template: dict[str, Any],
    arguments: dict[str, Any],
    title: str = "",
    punctuation: list[str] | None = None,
) -> dict[str, Any]:
    """Execute one modification.

    Args:
        poem: Current draft (body lines).
        template: Template dictionary.
        arguments: Tool arguments (modify_type / line / content).
        title: Current title (returned as the old value for the title type).
        punctuation: Current punctuation (returned as the old value for the
            punctuation type).

    Returns:
        For the line type, ``{"poem", "changed_line", "old_text", "new_text"}``;
        for the title type, ``{"title", "old_title"}``; for the punctuation
        type, ``{"punctuation", "old_punctuation"}``; failures return
        ``{"error": description}`` in every case.

    """
    modify_type = str(arguments.get("modify_type", "")).strip()
    if modify_type not in MODIFY_TYPES:
        return {
            "error": (
                f"Unknown modify type {modify_type!r}; expected line, title or "
                "punctuation"
            )
        }
    if modify_type == "line":
        return _modify_line(poem, template, arguments)
    if modify_type == "title":
        return _modify_title(arguments, title)
    return _modify_punctuation(template, arguments, punctuation)


def _modify_line(
    poem: list[str], template: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Replace a whole line after validating the line number and its meter.

    Args:
        poem: Current draft.
        template: Template dictionary.
        arguments: Tool arguments (line / content).

    Returns:
        Replacement result, or ``{"error": description}``.

    """
    if "line" not in arguments:
        return {"error": "The line type requires the line argument (0-based)"}
    try:
        line_idx = int(arguments["line"])
    except TypeError, ValueError:
        return {"error": "The line argument must be an integer"}
    content = arguments.get("content", "")
    if not isinstance(content, str):
        return {"error": "content for the line type must be a string"}
    if line_idx < 0 or line_idx >= len(poem):
        return {
            "error": (
                f"Line number {line_idx} is out of range; the draft has "
                f"{len(poem)} lines"
            )
        }

    result = MeterValidator().validate_line(content, line_idx, template)
    if not result.passed:
        return {"error": result.errors}

    old_text = poem[line_idx]
    new_poem = list(poem)
    new_poem[line_idx] = content
    return {
        "poem": new_poem,
        "changed_line": line_idx,
        "old_text": old_text,
        "new_text": content,
    }


def _modify_title(arguments: dict[str, Any], title: str) -> dict[str, Any]:
    """Replace the title (it must not be empty after stripping whitespace).

    Args:
        arguments: Tool arguments (content).
        title: Current title.

    Returns:
        ``{"title", "old_title"}`` or ``{"error": description}``.

    """
    content = arguments.get("content", "")
    if not isinstance(content, str):
        return {"error": "content for the title type must be a string"}
    new_title = content.strip()
    if not new_title:
        return {"error": "Title cannot be empty"}
    return {"title": new_title, "old_title": title}


def _modify_punctuation(
    template: dict[str, Any],
    arguments: dict[str, Any],
    punctuation: list[str] | None,
) -> dict[str, Any]:
    """Replace the punctuation list (its length must equal the meter line count).

    Args:
        template: Template dictionary (provides the meter line count).
        arguments: Tool arguments (content).
        punctuation: Current punctuation.

    Returns:
        ``{"punctuation", "old_punctuation"}`` or ``{"error": description}``.

    """
    content = arguments.get("content")
    if not isinstance(content, list) or not all(
        isinstance(item, str) for item in content
    ):
        return {"error": "content for the punctuation type must be a list of strings"}
    expected = int(template.get("lines", len(content)))
    if len(content) != expected:
        return {"error": f"Expected {expected} punctuation items, got {len(content)}"}
    return {
        "punctuation": list(content),
        "old_punctuation": list(punctuation or []),
    }
