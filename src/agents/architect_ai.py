# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Poem-sequence architect: planning for multiple poems (Step 1).

The architect AI repeatedly calls planning tools (set_sequence_title / add_poem /
set_poem_prompt) in one planning session; once it stops calling tools, every poem
is checked for a self-contained writing brief, and missing briefs are fed back as
reminders to keep filling in. If the plan is still incomplete after the maximum
number of rounds, it is returned as incomplete.
"""

import json
from dataclasses import dataclass
from typing import Any

from ..templates import list_dicts
from ..tools.planning import (
    PLANNING_TOOLS,
    PlanState,
    SequencePoemPlan,
    execute_add_poem,
    execute_set_poem_prompt,
    execute_set_sequence_title,
    missing_prompt_indices,
)
from .base import LLMClient, Message


@dataclass
class PlanResult:
    """Result of a poem-sequence plan."""

    completed: bool
    title: str
    poems: list[SequencePoemPlan]
    log: str = ""


def _catalog_text(catalog: list[dict[str, Any]]) -> str:
    """Render the template catalog as prompt text.

    Args:
        catalog: list_dicts() result.

    Returns:
        Multi-line template catalog text.

    """
    lines: list[str] = []
    for item in catalog:
        lines.append(
            f"- {item['key']}: {item['display_name']}; "
            f"{item.get('lines')} lines; syllables per line "
            f"{item.get('syllables_per_line')}"
        )
    return "\n".join(lines)


def _build_architect_system(topic: str, catalog: list[dict[str, Any]]) -> str:
    """Build the architect system prompt.

    Args:
        topic: Overall goal of the poem sequence given by the user.
        catalog: Template catalog.

    Returns:
        System prompt text.

    """
    return (
        "You are a poem-sequence architect. Break the user's overall intent "
        "into a group of poems (2-6 recommended) that are independent yet "
        "echo one another as a whole, and specify a meter template and "
        "self-contained creative requirements for each poem.\n\n"
        f"[Sequence goal]\n{topic}\n\n"
        "[Available meter templates]\n"
        f"{_catalog_text(catalog)}\n\n"
        "Complete the plan by calling tools in the following steps:\n"
        "1. First call set_sequence_title to set the overall sequence title;\n"
        "2. Use add_poem to add each poem's title and meter template key (the "
        "key must come from the list above);\n"
        "3. Use set_poem_prompt to write detailed, self-contained creative "
        "requirements for each poem (theme, imagery, emotion, structural "
        "points, etc.).\n\n"
        "Note: every poem's creative requirements must be self-contained; do "
        'not use cross-poem references such as "see poem N" or "reuse the '
        'theme of an earlier poem"; write any echoed imagery directly into '
        "the requirements of that poem.\n"
        "Once all poems have been added and their creative requirements "
        "written, stop calling tools."
    )


def _build_fixed_architect_system(
    topic: str, catalog: list[dict[str, Any]], poems: list[SequencePoemPlan]
) -> str:
    """Build the architect prompt for the "fixed poems/meter" mode.

    Args:
        topic: Overall goal of the poem sequence.
        catalog: Template catalog.
        poems: Pre-fixed poem list (including meter).

    Returns:
        System prompt text.

    """
    names = {str(item["key"]): str(item["name"]) for item in catalog}
    listing = "\n".join(
        f"- index {i}: poem {i + 1}, meter {names.get(p.template_key, p.template_key)}"
        for i, p in enumerate(poems)
    )
    return (
        "You are a poem-sequence architect. For this sequence, the number of "
        "poems and each poem's meter are fixed by the user; do not add or "
        "remove poems.\n\n"
        f"[Sequence goal]\n{topic}\n\n"
        "[Fixed poem list]\n"
        f"{listing}\n\n"
        "Call tools in the following steps:\n"
        "1. Call set_sequence_title to set the overall sequence title;\n"
        "2. For each poem in turn, call set_poem_prompt (index starts at 0) "
        "and write detailed, self-contained creative requirements (theme, "
        "imagery, emotion, structural points, etc.).\n\n"
        "Note: every poem's creative requirements must be self-contained; do "
        'not use cross-poem references such as "see poem N" or "reuse the '
        'theme of an earlier poem"; write any echoed imagery directly into '
        "the requirements of that poem.\n"
        "Once every poem's creative requirements are written, stop calling "
        "tools."
    )


class SequenceArchitect:
    """Sequence architect: produce the sequence title and writing briefs via tools."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the architect.

        Args:
            config: {"base_url", "api_key", "model"}.

        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def plan(
        self,
        topic: str,
        catalog: list[dict[str, Any]] | None = None,
        max_rounds: int = 12,
        poems: list[SequencePoemPlan] | None = None,
    ) -> PlanResult:
        """Run poem-sequence planning (ReAct: call tools → check → remind).

        Args:
            topic: Overall goal of the poem sequence.
            catalog: Template catalog (defaults to the registry).
            max_rounds: Maximum number of planning rounds.
            poems: Pre-fixed poem list (including meter). When provided, add_poem
                is no longer exposed to the AI; it is only asked to set the
                sequence title and each poem's writing brief.

        Returns:
            PlanResult(completed, title, poems, log).

        """
        if catalog is None:
            catalog = list_dicts()
        valid_keys = {str(item["key"]) for item in catalog}
        fixed = poems is not None
        if fixed:
            tools = [
                tool
                for tool in PLANNING_TOOLS
                if tool["function"]["name"] != "add_poem"
            ]
            state = PlanState(poems=list(poems or []))
            system_prompt = _build_fixed_architect_system(topic, catalog, state.poems)
        else:
            tools = list(PLANNING_TOOLS)
            state = PlanState()
            system_prompt = _build_architect_system(topic, catalog)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Begin planning the poem sequence."},
        ]
        detail: list[str] = []

        for round_idx in range(1, max_rounds + 1):
            response = self.client.chat(messages, tools=tools)
            if not response["tool_calls"]:
                problem = self._plan_problem(state)
                if problem is None:
                    return PlanResult(
                        True, state.title, list(state.poems), "\n".join(detail)
                    )
                messages.append(LLMClient.assistant_to_message(response))
                messages.append({"role": "user", "content": problem})
                detail.append(f"[round {round_idx}] reminder: {problem}")
                continue

            results: dict[str, dict[str, Any]] = {}
            for tool_call in response["tool_calls"]:
                name = str(tool_call["name"])
                args = tool_call["arguments"]
                if name == "set_sequence_title":
                    result = execute_set_sequence_title(state, args)
                elif name == "add_poem":
                    if fixed:
                        result = {
                            "error": "The poem count is fixed for this sequence; "
                            "do not add poems"
                        }
                    else:
                        result = execute_add_poem(state, args, valid_keys)
                elif name == "set_poem_prompt":
                    result = execute_set_poem_prompt(state, args)
                else:
                    result = {"error": f"Unknown planning tool {name}"}
                results[tool_call["id"]] = result
                detail.append(f"[round {round_idx}] {name}: {result}")

            messages.append(LLMClient.assistant_to_message(response))
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(results[tc["id"]], ensure_ascii=False),
                }
                for tc in response["tool_calls"]
            )

        return PlanResult(False, state.title, list(state.poems), "\n".join(detail))

    @staticmethod
    def _plan_problem(state: PlanState) -> str | None:
        """Check whether the plan is complete.

        Args:
            state: Planning state.

        Returns:
            Reminder text when more work is needed; None when complete.

        """
        if not state.title:
            return "First call set_sequence_title to set the overall sequence title."
        if not state.poems:
            return (
                "First call add_poem to add at least one poem (and specify a "
                "meter template key)."
            )
        missing = missing_prompt_indices(state)
        if missing:
            listing = ", ".join(
                f'poem {i + 1} "{state.poems[i].title}"' for i in missing
            )
            return (
                f"The following poems have no creative requirements yet: {listing}. "
                "Call set_poem_prompt to complete them, then stop calling tools."
            )
        return None
