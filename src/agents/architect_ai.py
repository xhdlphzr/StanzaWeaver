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
            f"- {item['key']}：{item['display_name']}；"
            f"{item.get('lines')} 行；每行音节 {item.get('syllables_per_line')}"
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
        "你是一位诗组架构师。请把用户的总体意图拆解为一组（建议 2-6 首）"
        "彼此独立又整体呼应的诗，并为每首指定格律模板与自足的创作要求。\n\n"
        f"【诗组总目标】\n{topic}\n\n"
        "【可用格律模板】\n"
        f"{_catalog_text(catalog)}\n\n"
        "请按以下步骤调用工具完成规划：\n"
        "1. 先调用 set_sequence_title 设定诗组总标题；\n"
        "2. 用 add_poem 逐首添加诗题与格律模板 key（必须来自上面的清单）；\n"
        "3. 用 set_poem_prompt 为每首写入详细、自足的创作要求（主题、意象、"
        "情感、结构要点等）。\n\n"
        "注意：每首的创作要求必须自足，不得写“参见第 N 首”“沿用前首主题”"
        "这类跨首指代；需要呼应的意象请直接写进本首要求。\n"
        "当所有诗都已添加并写好创作要求后，停止调用工具即可。"
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
        f"- index {i}：第{i + 1}首，格律 {names.get(p.template_key, p.template_key)}"
        for i, p in enumerate(poems)
    )
    return (
        "你是一位诗组架构师。本次诗组的诗数与每首格律已由用户固定，"
        "请不要再新增或删除诗。\n\n"
        f"【诗组总目标】\n{topic}\n\n"
        "【固定诗单】\n"
        f"{listing}\n\n"
        "请按以下步骤调用工具：\n"
        "1. 调用 set_sequence_title 设定诗组总标题；\n"
        "2. 依次为每首调用 set_poem_prompt（index 从 0 开始），写入详细、"
        "自足的创作要求（主题、意象、情感、结构要点等）。\n\n"
        "注意：每首的创作要求必须自足，不得写“参见第 N 首”“沿用前首主题”"
        "这类跨首指代；需要呼应的意象请直接写进本首要求。\n"
        "当所有诗的创作要求都写好后，停止调用工具即可。"
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
            {"role": "user", "content": "请开始规划诗组。"},
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
            return "请先调用 set_sequence_title 设定诗组总标题。"
        if not state.poems:
            return "请先调用 add_poem 至少添加一首诗（并指定格律模板 key）。"
        missing = missing_prompt_indices(state)
        if missing:
            listing = "、".join(
                f"第{i + 1}首《{state.poems[i].title}》" for i in missing
            )
            return (
                f"以下诗尚未设置创作要求：{listing}。"
                "请调用 set_poem_prompt 补齐后停止调用工具。"
            )
        return None
