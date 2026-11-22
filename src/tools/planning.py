# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Sequence planning tools (OpenAI Function Calling) and execution.

The architect AI plans a sequence with three tools: set_sequence_title first
sets the overall title, add_poem then adds each poem's title and meter
template, and set_poem_prompt finally writes self-contained detailed creative
requirements for each poem (cross-poem references such as "see poem N" are not
allowed).
"""

from dataclasses import dataclass, field
from typing import Any

SET_SEQUENCE_TITLE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_sequence_title",
        "description": "Set the overall sequence title; keep it short and refined.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Overall sequence title"},
            },
            "required": ["title"],
        },
    },
}

ADD_POEM_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "add_poem",
        "description": (
            "Add a poem to the sequence with its title and a meter template key "
            "(the key must come from the provided template list)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of this poem"},
                "template_key": {
                    "type": "string",
                    "description": "Meter template key (from the template list)",
                },
            },
            "required": ["title", "template_key"],
        },
    },
}

SET_POEM_PROMPT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_poem_prompt",
        "description": (
            "Write self-contained detailed creative requirements for an added "
            "poem (theme, imagery, emotion, structural points, etc.). Do not use "
            'cross-poem references such as "see poem N"; write everything needed '
            "directly into this poem."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "Poem index (0-based)"},
                "prompt": {
                    "type": "string",
                    "description": "Detailed creative requirements for this poem",
                },
            },
            "required": ["index", "prompt"],
        },
    },
}

PLANNING_TOOLS: list[dict[str, Any]] = [
    SET_SEQUENCE_TITLE_TOOL,
    ADD_POEM_TOOL,
    SET_POEM_PROMPT_TOOL,
]


@dataclass
class SequencePoemPlan:
    """Plan of one poem in the sequence."""

    title: str
    template_key: str
    prompt: str = ""


@dataclass
class PlanState:
    """Mutable state during planning."""

    title: str = ""
    poems: list[SequencePoemPlan] = field(default_factory=list)


def execute_set_sequence_title(
    state: PlanState, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_sequence_title.

    Args:
        state: Planning state.
        arguments: Tool arguments (title).

    Returns:
        ok or error result dictionary.

    """
    title = str(arguments.get("title", "")).strip()
    if not title:
        return {"error": "Sequence title cannot be empty"}
    state.title = title
    return {"status": "ok", "title": title}


def execute_add_poem(
    state: PlanState, arguments: dict[str, Any], valid_keys: set[str]
) -> dict[str, Any]:
    """Execute add_poem.

    Args:
        state: Planning state.
        arguments: Tool arguments (title / template_key).
        valid_keys: Set of available meter template keys.

    Returns:
        ok result (with index) or error result dictionary.

    """
    title = str(arguments.get("title", "")).strip()
    template_key = str(arguments.get("template_key", "")).strip()
    if not title:
        return {"error": "Poem title cannot be empty"}
    if template_key not in valid_keys:
        return {"error": f"Unknown meter template key: {template_key!r}"}
    state.poems.append(SequencePoemPlan(title=title, template_key=template_key))
    return {"status": "ok", "index": len(state.poems) - 1, "title": title}


def execute_set_poem_prompt(
    state: PlanState, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute set_poem_prompt.

    Args:
        state: Planning state.
        arguments: Tool arguments (index / prompt).

    Returns:
        ok or error result dictionary.

    """
    try:
        index = int(arguments.get("index", -1))
    except TypeError, ValueError:
        return {"error": "Poem index must be an integer"}
    if index < 0 or index >= len(state.poems):
        return {
            "error": (
                f"Poem index {index} is out of range; there are "
                f"{len(state.poems)} poems"
            )
        }
    prompt = str(arguments.get("prompt", "")).strip()
    if not prompt:
        return {"error": "Creative requirements cannot be empty"}
    state.poems[index].prompt = prompt
    return {"status": "ok", "index": index}


def missing_prompt_indices(state: PlanState) -> list[int]:
    """Return the poem indices that have no creative requirements yet.

    Args:
        state: Planning state.

    Returns:
        List of 0-based indices whose prompt is missing.

    """
    return [i for i, poem in enumerate(state.poems) if not poem.prompt.strip()]


def render_plan(state: PlanState, names: dict[str, str] | None = None) -> str:
    """Render the planning state as readable text.

    Args:
        state: Planning state.
        names: Mapping from template key to display name.

    Returns:
        Multi-line plan text.

    """
    names = names or {}
    lines = [f'Sequence "{state.title or "Untitled"}" ({len(state.poems)} poems)']
    for i, poem in enumerate(state.poems, 1):
        label = names.get(poem.template_key, poem.template_key)
        lines.append(f'  {i}. "{poem.title}" [{label}]')
        lines.append(f"     {poem.prompt or '(no creative requirements set)'}")
    return "\n".join(lines)
