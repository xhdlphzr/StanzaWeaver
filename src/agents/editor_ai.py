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


# --------------------------------------------------------------------------- #
# 模板代码 AI 转写（跨语言转化时可选）
# --------------------------------------------------------------------------- #

_SUBMIT_CODE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_code",
        "description": (
            "提交改写后的模板校验 Python 代码。代码会被插入生成模板的 "
            "validate_full 中（不要包含 def/class 定义）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "改写后的 Python 代码（填充式，可操作 errors/poem/syllables）",
                },
                "notes": {
                    "type": "string",
                    "description": "改写说明（哪些规则保留、哪些在目标语言中降级/舍弃）",
                },
            },
            "required": ["code"],
        },
    },
}

_ATTRIBUTE_LABELS: dict[str, str] = {
    "tone": "平仄（tone）",
    "stress": "轻重（stress）",
    "length": "长短（length）",
}

_VALUE_LABELS: dict[str, str] = {
    "平": "平声",
    "仄": "仄声",
    "heavy": "重读",
    "light": "轻读",
    "long": "长音",
    "short": "短音",
}


def format_value_mapping(
    source_language: str, target_language: str, mapping: dict[str, str]
) -> str:
    """把属性值映射格式化为给 AI 的人类可读说明.

    Args:
        source_language: 源语言代码。
        target_language: 目标语言代码。
        mapping: 源属性值 → 目标属性值的映射。

    Returns:
        多行说明文本（含属性维度与每个值的对应关系）。

    """
    from ..templates.convert import constraint_scheme

    source_attribute, _ = constraint_scheme(source_language)
    target_attribute, _ = constraint_scheme(target_language)
    lines: list[str] = []
    if source_attribute or target_attribute:
        lines.append(
            f"- 属性维度：{_ATTRIBUTE_LABELS.get(source_attribute, source_attribute or '无')}"
            f" → {_ATTRIBUTE_LABELS.get(target_attribute, target_attribute or '无')}"
        )
    if not target_attribute:
        lines.append("- 目标语言没有逐位音节属性；映射值仅用于理解源规则。")
        return "\n".join(lines)
    if not mapping:
        lines.append("- 未提供具体属性值映射；源语言属性值在目标语言中保持自由。")
        return "\n".join(lines)
    for source_value in sorted(mapping):
        target_value = mapping[source_value]
        source_label = _VALUE_LABELS.get(source_value, source_value)
        target_label = _VALUE_LABELS.get(target_value, target_value)
        lines.append(
            f"- {source_value}（{source_label}）→ {target_value}（{target_label}）"
        )
    return "\n".join(lines)


def _build_rewrite_system(
    source_language: str,
    target_language: str,
    mapping: dict[str, str],
    source_code: str,
    target_spec: dict[str, Any],
    rule_note: str = "",
) -> str:
    """构造模板代码转写的系统提示.

    Args:
        source_language: 源语言代码。
        target_language: 目标语言代码。
        mapping: 源属性值 → 目标属性值的映射。
        source_code: 源模板代码。
        target_spec: 确定性转化得到的目标模板规格。
        rule_note: 模板规则描述。

    Returns:
        系统提示文本。

    """
    spec = {
        "lines": target_spec.get("lines"),
        "syllables_per_line": target_spec.get("syllables_per_line"),
        "alternatives": target_spec.get("alternatives"),
        "rhyme_scheme": target_spec.get("rhyme_scheme"),
        "rhyme_distinct": target_spec.get("rhyme_distinct"),
        "structural_rules": target_spec.get("structural_rules"),
    }
    note_section = f"\n【模板规则描述】\n{rule_note}\n" if rule_note.strip() else ""
    return (
        "你是一位熟悉多语言诗歌格律的 Python 工程师。请把下面源语言模板的校验代码"
        f"改写为目标语言的版本（{source_language} → {target_language}），使其在新语言的"
        "音节属性与押韵体系下保持原有规则的意图。\n\n"
        "【语言与属性值映射】\n"
        f"{format_value_mapping(source_language, target_language, mapping)}\n"
        "注意：把代码中的源语言属性键与属性值按上面的映射替换为目标语言的属性键与值"
        "（例如把“平”改成“轻/重”对应的目标值）；押韵逻辑如需重写，请使用目标语言的"
        "通用押韵接口而不要沿用源语言的韵部常量/语音学函数。\n"
        f"{note_section}"
        "【目标模板的声明式规格】\n"
        f"{json.dumps(spec, ensure_ascii=False, indent=2)}\n\n"
        "【代码运行环境】\n"
        "改写后的代码会插入生成模板的 validate_full 中，可用以下名称：\n"
        "- errors: list[str]，错误信息列表（追加错误）；\n"
        "- poem: list[str]，诗行；\n"
        "- syllables: list[list[Syllable]]，每行音节（含目标语言属性）；\n"
        "- rules：目标语言模板模块别名，可调用其中的辅助函数（如有）；\n"
        "- self.structural_rules：目标模板的数据化结构规则（如存在）。\n"
        "不要使用 def/class、不要读写文件或访问网络；不要 import 源语言模块。\n\n"
        "【源模板代码】\n"
        "```python\n"
        f"{source_code}\n"
        "```\n\n"
        "请调用 submit_code 工具提交改写后的填充式代码（code）与改写说明（notes）。"
    )


class TemplateCodeRewriter:
    """用模板 AI 把源模板校验代码转写为目标语言版本."""

    def __init__(self, config: dict[str, Any]):
        """初始化代码转写器.

        Args:
            config: {"base_url", "api_key", "model"}。

        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def rewrite(
        self,
        source_language: str,
        target_language: str,
        mapping: dict[str, str],
        source_code: str,
        target_spec: dict[str, Any],
        rule_note: str = "",
        max_rounds: int = 2,
    ) -> dict[str, Any]:
        """把源模板代码转写为目标语言代码（调用工具输出，带语法校验）.

        Args:
            source_language: 源语言代码。
            target_language: 目标语言代码。
            mapping: 源属性值 → 目标属性值的映射。
            source_code: 源模板代码。
            target_spec: 确定性转化得到的目标模板规格。
            rule_note: 模板规则描述。
            max_rounds: 最大尝试轮数。

        Returns:
            {"status": "ok", "code", "notes"} 或 {"status": "error", "message"}。
        """
        messages: list[Message] = [
            {
                "role": "system",
                "content": _build_rewrite_system(
                    source_language,
                    target_language,
                    mapping,
                    source_code,
                    target_spec,
                    rule_note,
                ),
            },
            {
                "role": "user",
                "content": "请按映射与运行环境要求改写源模板代码，并调用 submit_code 提交。",
            },
        ]
        for _ in range(max_rounds):
            try:
                response = self.client.chat(messages, tools=[_SUBMIT_CODE_TOOL])
            except Exception as e:  # noqa: BLE001 - 代码转写兜底：调用失败回报给前端
                return {"status": "error", "message": f"模板代码 AI 转写失败: {e}"}
            arguments: dict[str, Any] | None = None
            for tool_call in response.get("tool_calls") or []:
                if str(tool_call.get("name")) == "submit_code":
                    raw = tool_call.get("arguments")
                    arguments = raw if isinstance(raw, dict) else {}
                    break
            if arguments is not None:
                code = str(arguments.get("code", "") or "").strip()
                notes = str(arguments.get("notes", "") or "")
                if not code:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": "提交的代码为空，请重新调用 submit_code。",
                        }
                    )
                    continue
                try:
                    compile(code, "<ai-template-code>", "exec")
                except SyntaxError as e:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"代码存在语法错误（{e}），请修正后重新调用 submit_code 提交。"
                            ),
                        }
                    )
                    continue
                return {"status": "ok", "code": code, "notes": notes}
            messages.append(LLMClient.assistant_to_message(response))
            messages.append(
                {
                    "role": "user",
                    "content": "请务必调用 submit_code 工具提交改写后的代码。",
                }
            )
        return {
            "status": "error",
            "message": "模板代码 AI 转写未能在限定轮数内给出合法代码",
        }
