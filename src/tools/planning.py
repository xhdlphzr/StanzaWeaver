# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""诗组规划工具（OpenAI Function Calling）与执行.

架构师 AI 通过三个工具规划诗组：先 set_sequence_title 设定总标题，再用
add_poem 逐首添加诗题与格律模板，最后用 set_poem_prompt 为每首写入自足的
详细创作要求（不得使用“参见第 N 首”这类跨首指代）。
"""

from dataclasses import dataclass, field
from typing import Any

SET_SEQUENCE_TITLE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_sequence_title",
        "description": "设置诗组的总标题，简短精炼。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "诗组总标题"},
            },
            "required": ["title"],
        },
    },
}

ADD_POEM_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "add_poem",
        "description": "向诗组添加一首诗，指定诗题与格律模板 key（必须来自给定模板清单）。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "本首诗题"},
                "template_key": {
                    "type": "string",
                    "description": "格律模板 key（来自模板清单）",
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
            "为已添加的某首诗写入自足的详细创作要求（主题、意象、情感、结构要点等）。"
            "不得使用“参见第N首”这类跨首指代，应把所需内容直接写入本首。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "诗序号（从0开始）"},
                "prompt": {"type": "string", "description": "本首的详细创作要求"},
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
    """诗组中单首诗的规划."""

    title: str
    template_key: str
    prompt: str = ""


@dataclass
class PlanState:
    """规划过程中的可变状态."""

    title: str = ""
    poems: list[SequencePoemPlan] = field(default_factory=list)


def execute_set_sequence_title(
    state: PlanState, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_sequence_title.

    Args:
        state: 规划状态。
        arguments: 工具参数（title）。

    Returns:
        ok 或 error 结果字典。

    """
    title = str(arguments.get("title", "")).strip()
    if not title:
        return {"error": "诗组标题不能为空"}
    state.title = title
    return {"status": "ok", "title": title}


def execute_add_poem(
    state: PlanState, arguments: dict[str, Any], valid_keys: set[str]
) -> dict[str, Any]:
    """执行 add_poem.

    Args:
        state: 规划状态。
        arguments: 工具参数（title / template_key）。
        valid_keys: 可用的格律模板 key 集合。

    Returns:
        ok（含 index）或 error 结果字典。

    """
    title = str(arguments.get("title", "")).strip()
    template_key = str(arguments.get("template_key", "")).strip()
    if not title:
        return {"error": "诗题不能为空"}
    if template_key not in valid_keys:
        return {"error": f"未知格律模板 key: {template_key!r}"}
    state.poems.append(SequencePoemPlan(title=title, template_key=template_key))
    return {"status": "ok", "index": len(state.poems) - 1, "title": title}


def execute_set_poem_prompt(
    state: PlanState, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_poem_prompt.

    Args:
        state: 规划状态。
        arguments: 工具参数（index / prompt）。

    Returns:
        ok 或 error 结果字典。

    """
    try:
        index = int(arguments.get("index", -1))
    except TypeError, ValueError:
        return {"error": "诗序号 index 必须是整数"}
    if index < 0 or index >= len(state.poems):
        return {"error": f"诗序号 {index} 越界，当前共 {len(state.poems)} 首"}
    prompt = str(arguments.get("prompt", "")).strip()
    if not prompt:
        return {"error": "创作要求不能为空"}
    state.poems[index].prompt = prompt
    return {"status": "ok", "index": index}


def missing_prompt_indices(state: PlanState) -> list[int]:
    """返回尚未设置创作要求的诗序号.

    Args:
        state: 规划状态。

    Returns:
        缺少 prompt 的 0-based 序号列表。

    """
    return [i for i, poem in enumerate(state.poems) if not poem.prompt.strip()]


def render_plan(state: PlanState, names: dict[str, str] | None = None) -> str:
    """把规划状态渲染为可读文本.

    Args:
        state: 规划状态。
        names: 模板 key -> 显示名映射。

    Returns:
        多行计划文本。

    """
    names = names or {}
    lines = [f"诗组《{state.title or '未命名'}》（共 {len(state.poems)} 首）"]
    for i, poem in enumerate(state.poems, 1):
        label = names.get(poem.template_key, poem.template_key)
        lines.append(f"  {i}. 《{poem.title}》[{label}]")
        lines.append(f"     {poem.prompt or '（未设置创作要求）'}")
    return "\n".join(lines)
