# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""模板编辑 AI：通过工具对话式配置自定义模板.

用户在自定义模板弹窗底部描述想要的模板，本代理循环调用工具（设置模板
信息、音节数、约束种类、逐位约束、韵式、自定义代码），把每次思考、
回答与工具调用通过回调实时推给前端；AI 满足条件后可调用 submit_template
交由服务端落盘注册。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..tools.template_tools import (
    TEMPLATE_TOOLS,
    TemplateDraft,
    draft_from_payload,
    execute_template_tool,
)
from .base import LLMClient, Message

#: 模板编辑 AI 的最大工具轮数。
MAX_EDITOR_ROUNDS = 12

EditorEvent = dict[str, Any]
EmitCallback = Callable[[EditorEvent], None] | None


def _build_editor_system(draft: TemplateDraft) -> str:
    """构造模板编辑 AI 的系统提示.

    Args:
        draft: 当前模板草稿。

    Returns:
        系统提示文本。

    """
    draft_json = json.dumps(draft.to_payload(), ensure_ascii=False, indent=2)
    return (
        "你是一位格律模板配置助手。用户会用自然语言描述想要的诗歌格律，"
        "你需要调用工具把它配置为 StanzaWeaver 的自定义模板。\n\n"
        "【工具说明】\n"
        "- set_template_info：设置名称/语言/行数。语言决定逐位约束属性："
        "zh 用平/仄；en、it 用 light/heavy；la 用 long/short；fr 无逐位属性。\n"
        "- set_syllables_per_line：设置每行音节数（长度须等于行数）。\n"
        "- set_constraint_kind_count：设置约束种类数量；多种约束之间是“或”"
        "关系，生成时满足任意一种即可（例如绝句的仄起/平起四种格式）。\n"
        "- set_syllable_constraints：按“第几种约束 → 每行 → 每音节”填写规范值，"
        "空串表示该位自由；支持中文别名 重/轻/长/短。\n"
        "- set_from_template：从已有模板转化语言——行数/音节数/约束种类/押韵韵式/"
        "自定义代码原样复制，仅按 mapping（源属性值 → 目标属性值）转换逐位约束，"
        '例如 {"平": "heavy"}。\n'
        "- set_rule_description：填写模板规则描述（自然语言的体裁/句式/对仗/结构"
        "要求等）；这段文字会作为 prompt 提供给生成诗歌的写作 AI。\n"
        "- set_rhyme_scheme：设置韵式，例如 ABAB CDCD EFEF GG；相同字母的行押韵，"
        "'-' 表示该行不押韵；distinct=true 表示不同韵组须互不相同。\n"
        "- set_custom_code：写入额外的 Python 整体校验代码（可选）。\n"
        "- get_template_draft：读取当前完整草稿。\n"
        "- submit_template：提交，服务端会创建并注册模板。\n\n"
        "【当前草稿】\n"
        f"{draft_json}\n\n"
        "请优先把用户描述完整转化为工具调用；信息不全时可做合理推断。"
        "全部配置完成后调用 submit_template 提交。"
        "如果用户只是闲聊或询问，请简要回答并说明下一步可以如何配置。"
    )


@dataclass
class EditorResult:
    """一次模板编辑会话的结果."""

    draft: TemplateDraft
    submitted: bool
    message: str


class TemplateEditorAI:
    """模板编辑 AI 代理（独立 LLM 端点/模型）."""

    def __init__(self, config: dict[str, Any]):
        """初始化模板编辑 AI.

        Args:
            config: {"base_url", "api_key", "model"}。

        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def edit(
        self,
        prompt: str,
        payload: dict[str, Any] | None = None,
        emit: EmitCallback = None,
        max_rounds: int = MAX_EDITOR_ROUNDS,
    ) -> EditorResult:
        """执行模板编辑对话（循环调用工具，直到提交或无工具调用）.

        Args:
            prompt: 用户对模板的自然语言描述。
            payload: 当前模板草稿（前端表单状态）。
            emit: 事件回调（thinking/message/tool/info）。
            max_rounds: 最大工具轮数。

        Returns:
            EditorResult(draft, submitted, message)。

        """

        def push(event: EditorEvent) -> None:
            """安全推送一条编辑事件到前端.

            Args:
                event: 事件字典。

            """
            if emit:
                emit(event)

        draft = draft_from_payload(payload or {})
        messages: list[Message] = [
            {"role": "system", "content": _build_editor_system(draft)},
            {"role": "user", "content": prompt},
        ]
        last_message = ""
        for round_idx in range(1, max_rounds + 1):
            try:
                response = self.client.chat(messages, tools=TEMPLATE_TOOLS)
            except Exception as e:  # noqa: BLE001 - 模板AI兜底：调用失败回报给前端
                push(
                    {
                        "type": "error",
                        "round": round_idx,
                        "content": f"模板AI调用失败: {e}",
                    }
                )
                return EditorResult(draft, False, f"模板AI调用失败: {e}")

            reasoning = response.get("reasoning_content")
            if reasoning:
                push(
                    {
                        "type": "thinking",
                        "round": round_idx,
                        "content": str(reasoning),
                    }
                )
            content = str(response.get("content") or "").strip()
            if content:
                last_message = content
                push({"type": "message", "round": round_idx, "content": content})

            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                if not draft.name:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "请继续调用工具完成模板配置：先 set_template_info "
                                "设置名称/语言/行数，再设置约束等；完成后调用 submit_template。"
                            ),
                        }
                    )
                    continue
                return EditorResult(draft, False, content or "已根据描述更新模板配置")

            results_by_id: dict[str, dict[str, Any]] = {}
            submitted = False
            for tool_call in tool_calls:
                name = str(tool_call["name"])
                arguments = tool_call.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                result = execute_template_tool(draft, name, arguments)
                results_by_id[str(tool_call["id"])] = result
                push(
                    {
                        "type": "tool",
                        "round": round_idx,
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                if name == "submit_template" and result.get("status") == "submitted":
                    submitted = True

            if submitted:
                return EditorResult(draft, True, content or "模板已提交，正在创建...")

            messages.append(LLMClient.assistant_to_message(response))
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": str(tc["id"]),
                    "content": json.dumps(
                        results_by_id.get(str(tc["id"]), {"error": "工具未执行"}),
                        ensure_ascii=False,
                    ),
                }
                for tc in tool_calls
            )

        push({"type": "info", "content": f"已达到最大轮数（{max_rounds}），停止编辑"})
        return EditorResult(draft, False, last_message or "已达到最大轮数，停止编辑")
