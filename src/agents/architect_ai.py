# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""诗组架构师：多首诗的规划（Step 1）.

架构师 AI 在一个规划会话里循环调用规划工具（set_sequence_title / add_poem /
set_poem_prompt）；停止调用工具后检查每个诗题是否都有自足的创作要求，缺失则
回灌提醒继续补齐，达到最大轮数仍未完整则返回未完成。
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
    """诗组规划结果."""

    completed: bool
    title: str
    poems: list[SequencePoemPlan]
    log: str = ""


def _catalog_text(catalog: list[dict[str, Any]]) -> str:
    """把模板清单渲染为提示文本.

    Args:
        catalog: list_dicts() 结果。

    Returns:
        多行模板清单文本。

    """
    lines: list[str] = []
    for item in catalog:
        lines.append(
            f"- {item['key']}：{item['display_name']}；"
            f"{item.get('lines')} 行；每行音节 {item.get('syllables_per_line')}"
        )
    return "\n".join(lines)


def _build_architect_system(topic: str, catalog: list[dict[str, Any]]) -> str:
    """构造架构师的系统提示.

    Args:
        topic: 用户给诗组的总目标。
        catalog: 模板清单。

    Returns:
        系统提示文本。

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
    """构造“诗数/格律已固定”模式下的架构师提示.

    Args:
        topic: 诗组总目标。
        catalog: 模板清单。
        poems: 已预先固定的诗单（含格律）。

    Returns:
        系统提示文本。

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
    """诗组架构师：用规划工具产出诗组标题与每首诗的创作要求."""

    def __init__(self, config: dict[str, Any]):
        """初始化架构师.

        Args:
            config: {"base_url", "api_key", "model"}。

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
        """执行诗组规划（ReAct：调用工具 → 检查完整性 → 回灌提醒）.

        Args:
            topic: 诗组总目标。
            catalog: 模板清单（缺省读取注册表）。
            max_rounds: 最大规划轮数。
            poems: 预先固定的诗单（含格律）。提供时不再向 AI 暴露 add_poem，
                仅要求其设定诗组标题与每首创作要求。

        Returns:
            PlanResult(completed, title, poems, log)。

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
                detail.append(f"[第{round_idx}轮] 提醒: {problem}")
                continue

            results: dict[str, dict[str, Any]] = {}
            for tool_call in response["tool_calls"]:
                name = str(tool_call["name"])
                args = tool_call["arguments"]
                if name == "set_sequence_title":
                    result = execute_set_sequence_title(state, args)
                elif name == "add_poem":
                    if fixed:
                        result = {"error": "本次诗组诗数已固定，请勿新增诗"}
                    else:
                        result = execute_add_poem(state, args, valid_keys)
                elif name == "set_poem_prompt":
                    result = execute_set_poem_prompt(state, args)
                else:
                    result = {"error": f"未知规划工具 {name}"}
                results[tool_call["id"]] = result
                detail.append(f"[第{round_idx}轮] {name}: {result}")

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
        """检查规划是否完整.

        Args:
            state: 规划状态。

        Returns:
            需要继续补全时的提醒文本；完整时返回 None。

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
