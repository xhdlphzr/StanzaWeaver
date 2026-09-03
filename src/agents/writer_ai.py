# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""编写 AI：描述生成、初稿生成、ReAct 炼句循环。

炼句循环无轮数上限：AI 反复调用 search_words/refine_line/rewrite
修改诗句（每次修改后自动跑全部格律校验），直到调用 submit 提交。
连续多轮无进展时注入引导提示（不中断循环）。

当对话 token 数超过 COMPRESS_THRESHOLD 时自动压缩历史并重开新对话，
保留结构化摘要（目标/重要细节/工作状态/下一步行动）与当前诗稿。
"""

import json
from collections.abc import Callable
from typing import Any

from ..prosody.meter_validator import MeterValidator
from ..templates import format_count
from ..tools import SUBMIT_TOOL, WRITER_TOOLS
from ..tools.refine_line import execute_refine_line
from ..tools.search_words import execute_search_words
from .base import LLMClient, Message

CONTEXT_LIMIT = 200_000
COMPRESS_THRESHOLD = 180_000

ChunkCallback = Callable[[str], None] | None
StepCallback = Callable[[dict[str, Any]], None] | None
RefineResult = tuple[list[str], bool, list[dict[str, Any]], str, int]


def _fire_stream(cb: ChunkCallback, text: str) -> None:
    """安全触发流式回调（吞掉回调内部异常）。

    前端流回调失败不应中断生成流程。

    Args:
        cb: 回调函数。
        text: 回调文本。
    """
    if cb:
        try:
            cb(text)
        except Exception:  # noqa: S110, BLE001 - 有意吞掉回调异常，仅保证生成不中断
            pass


def _get_constraints_desc(template: dict[str, Any], template_obj: object = None) -> str:
    """获取格律约束描述文本。

    Args:
        template: 模板字典。
        template_obj: 模板对象。

    Returns:
        格律描述文本。
    """
    if template_obj is not None and hasattr(template_obj, "describe"):
        return str(template_obj.describe())
    language = str(template.get("language", "zh"))
    lines = int(template.get("lines", 4))
    syllables_per_line = template.get("syllables_per_line", [5] * lines)
    return (
        f"- 语言: {language}\n- 行数: {lines}\n"
        f"- 每行音节数: {', '.join(format_count(c) for c in syllables_per_line)}"
    )


def _build_draft_system(language: str, constraints_desc: str) -> str:
    """构造 Step 2 初稿生成的系统提示。

    Args:
        language: 语言代码。
        constraints_desc: 格律约束描述。

    Returns:
        系统提示文本。
    """
    return (
        f"你是一位精通{language}诗歌创作的AI诗人。\n"
        "请根据上面的主题描述，按照以下格律要求创作一首诗。\n"
        "\n"
        "【格律要求】\n"
        f"{constraints_desc}\n"
        "\n"
        "创作完成后，调用 submit 工具提交诗稿。系统会自动校验行数和音节数，\n"
        "不通过会返回具体错误，你需要根据错误调整后重新提交。\n"
        "\n"
        "你有以下工具可用: submit(提交诗稿)。"
    )


def _build_refine_system(constraints_desc: str, feedback: str = "") -> str:
    """构造 Step 3 炼句循环的系统提示。

    Args:
        constraints_desc: 格律约束描述。
        feedback: 用户/检查 AI 反馈。

    Returns:
        系统提示文本。
    """
    parts = [
        "请对上面的诗稿进行炼句优化。",
        "",
        "【格律要求】",
        constraints_desc,
        "",
    ]
    if feedback:
        parts.extend(["【反馈/建议】", feedback, ""])
    parts.extend(
        [
            (
                "你有以下工具可用: search_words(搜候选词), refine_line(重写某一行),"
                " rewrite(整体重写全诗), submit(提交定稿)。"
            ),
            "每次调用 refine_line 或 rewrite 后，系统会自动校验格律，不通过会返回具体错误。",
            "当你对全诗满意时，调用 submit 提交。",
        ]
    )
    return "\n".join(parts)


def _extract_poem_from_messages(messages: list[Message]) -> list[str]:
    """从对话历史中提取最近的诗稿行。

    在 assistant 消息的 content 中查找连续的非空行作为诗稿。

    Args:
        messages: 对话消息列表。

    Returns:
        提取的诗行列表。
    """
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            text = str(msg["content"])
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if lines:
                return lines
    return []


class WriterAI:
    """编写 AI：四步流水线的神经层（描述/初稿/炼句）。"""

    def __init__(self, config: dict[str, Any]):
        """初始化编写 AI。

        Args:
            config: {"base_url", "api_key", "model"}。
        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )
        self.validator = MeterValidator()

    def _compress_messages(
        self,
        messages: list[Message],
        description: str,
        poem: list[str],
        template: dict[str, Any],
        template_obj: object = None,
    ) -> None:
        """压缩对话历史：用 LLM 生成结构化摘要，替换当前消息列表。

        摘要包含：目标、重要细节、工作状态、下一步行动，以及当前诗稿。

        Args:
            messages: 要压缩的消息列表（就地修改）。
            description: 主题描述。
            poem: 当前诗稿。
            template: 模板字典。
            template_obj: 模板对象。
        """
        constraints_desc = _get_constraints_desc(template, template_obj)
        poem_text = "\n".join(poem) if poem else "（无）"
        compress_prompt = (
            "请将以下对话状态压缩为结构化摘要，保留所有关键信息以便继续工作。\n"
            "\n"
            "【当前诗稿】\n"
            f"{poem_text}\n"
            "\n"
            "【格律约束】\n"
            f"{constraints_desc}\n"
            "\n"
            "请按以下格式输出摘要:\n"
            "【目标】当前任务的核心目标\n"
            "【重要细节】关键信息、格律约束、已做出的重要决策\n"
            "【工作状态】\n"
            "  已完成: ...\n"
            "  进行中: ...\n"
            "  被阻塞: ...\n"
            "【下一步行动】建议的下一步具体操作"
        )
        summary_response = self.client.chat(
            [
                {"role": "system", "content": "你是一位诗歌创作助手，请压缩对话状态。"},
                {"role": "user", "content": compress_prompt},
            ]
        )
        summary_text = str(summary_response.get("content", "")).strip()
        messages.clear()
        messages.append(
            {
                "role": "system",
                "content": (
                    "以下是之前对话的压缩摘要，新对话从这里继续：\n\n"
                    f"{summary_text}\n\n"
                    "请根据以上摘要继续工作。当前诗稿如下："
                ),
            }
        )
        messages.append({"role": "user", "content": f"当前诗稿:\n{poem_text}"})

    def _check_and_compress(
        self,
        messages: list[Message],
        description: str,
        poem: list[str],
        template: dict[str, Any],
        template_obj: object = None,
    ) -> None:
        """检查 token 数，超过阈值时自动压缩对话历史。

        Args:
            messages: 消息列表。
            description: 主题描述。
            poem: 当前诗稿。
            template: 模板字典。
            template_obj: 模板对象。
        """
        token_count = self.client.count_tokens(messages)
        if token_count >= COMPRESS_THRESHOLD:
            self._compress_messages(messages, description, poem, template, template_obj)

    def generate_description(
        self,
        topic: str,
        messages: list[Message],
        on_stream: ChunkCallback = None,
    ) -> tuple[str, str]:
        """生成主题的现代文描述（Step 1）。

        Args:
            topic: 用户主题。
            messages: 共享对话消息列表（会被追加）。
            on_stream: 流式回调。

        Returns:
            (描述文本, 日志文本)。
        """
        messages.append(
            {
                "role": "system",
                "content": (
                    "你是一位诗歌创作助手。根据用户给出的主题，写一段100字以内的"
                    "现代文描述，包含意象、情感、内容概要。直接输出描述文本，不要加任何前缀。"
                ),
            }
        )
        messages.append({"role": "user", "content": f"主题: {topic}"})
        if on_stream:
            response = self.client.chat_stream(messages, on_chunk=on_stream)
        else:
            response = self.client.chat(messages)
        desc = str(response["content"]).strip()
        messages.append(LLMClient.assistant_to_message(response))
        return desc, desc

    def generate_draft(
        self,
        description: str,
        template: dict[str, Any],
        messages: list[Message],
        template_obj: object = None,
        max_attempts: int = 0,
        on_stream: ChunkCallback = None,
    ) -> tuple[list[str], str, str]:
        """生成初稿（Step 2，通过 submit 工具提交，无尝试次数上限）。

        Args:
            description: 主题描述。
            template: 模板字典。
            messages: 共享对话消息列表（会被追加）。
            template_obj: 模板对象。
            max_attempts: 已废弃，保留仅为接口兼容。
            on_stream: 流式回调。

        Returns:
            (诗稿, 标题, 日志文本)。
        """
        language = str(template.get("language", "zh"))
        lines = int(template.get("lines", 4))

        constraints_desc = _get_constraints_desc(template, template_obj)
        messages.append(
            {
                "role": "system",
                "content": _build_draft_system(language, constraints_desc),
            }
        )
        messages.append({"role": "user", "content": "请创作诗稿。"})

        detail_parts: list[str] = []
        poem: list[str] = []
        title: str = ""
        attempt = 0
        while True:
            attempt += 1
            if on_stream and attempt == 1:
                _fire_stream(on_stream, "[初稿] 思考中...")
            self._check_and_compress(
                messages, description, poem, template, template_obj
            )
            response = self.client.chat(messages, tools=[SUBMIT_TOOL])

            if response["tool_calls"]:
                for tc in response["tool_calls"]:
                    if tc["name"] == "submit":
                        title = str(tc["arguments"].get("title", "")).strip()
                        text = str(response.get("content", "")).strip()
                        if text:
                            poem = [ln.strip() for ln in text.split("\n") if ln.strip()]
                        else:
                            # AI 没有在 content 中输出诗稿，从历史中解析
                            poem = _extract_poem_from_messages(messages)

                        if not title:
                            result: dict[str, Any] = {
                                "error": "标题不能为空，请提供诗稿标题"
                            }
                        elif len(poem) != lines:
                            result = {"error": f"输出行数为{len(poem)}，期望{lines}行"}
                        else:
                            count_result = self.validator.validate_count_only(
                                poem, template
                            )
                            if count_result.passed:
                                result = {
                                    "status": "passed",
                                    "poem": poem,
                                    "title": title,
                                }
                            else:
                                result = {"error": "; ".join(count_result.errors)}

                        messages.append(LLMClient.assistant_to_message(response))
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": str(tc["id"]),
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )
                        detail_parts.append(f"submit: {result}")

                        if result.get("status") == "passed":
                            if on_stream:
                                _fire_stream(on_stream, "[初稿] 完成")
                            return poem, title, "\n\n".join(detail_parts)
                        continue

                continue

            # AI 没调 submit，解析文本内容
            text = str(response["content"]).strip()
            detail_parts.append(f"生成:\n{text}")
            poem = [ln.strip() for ln in text.split("\n") if ln.strip()]
            messages.append(LLMClient.assistant_to_message(response))

            if len(poem) != lines:
                messages.append(
                    {
                        "role": "user",
                        "content": f"输出行数为{len(poem)}行，期望{lines}行。请重新输出并调用 submit 提交。",
                    }
                )
                continue

            count_result = self.validator.validate_count_only(poem, template)
            if count_result.passed:
                messages.append(
                    {
                        "role": "user",
                        "content": "诗稿已通过校验，请调用 submit 工具提交。",
                    }
                )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": "格律校验未通过:\n"
                        + "\n".join(count_result.errors)
                        + "\n请修正后重新输出并调用 submit 提交。",
                    }
                )

    def refine(
        self,
        description: str,
        poem: list[str],
        template: dict[str, Any],
        messages: list[Message],
        template_obj: object = None,
        feedback: str = "",
        on_step: StepCallback = None,
        on_stream: ChunkCallback = None,
        start_round: int = 0,
    ) -> RefineResult:
        """ReAct 炼句循环（Step 3，无轮数上限，直到 submit 成功）。

        Args:
            description: 主题描述。
            poem: 当前诗稿。
            template: 模板字典。
            messages: 共享对话消息列表（会被追加）。
            template_obj: 模板对象。
            feedback: 用户/检查 AI 反馈。
            on_step: 每次工具执行后的回调。
            on_stream: 流式回调。
            start_round: 起始轮号（打回续轮用）。

        Returns:
            (诗稿, 是否提交, 工具历史, 日志, 执行轮数)。
        """
        current_poem = list(poem)
        constraints_desc = _get_constraints_desc(template, template_obj)
        messages.append(
            {
                "role": "system",
                "content": _build_refine_system(constraints_desc, feedback),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "请开始炼句优化。先用 search_words 搜候选词，然后必须至少调用一次"
                    " refine_line 或 rewrite 修改诗句，才能调用 submit 提交。"
                ),
            }
        )

        submitted = False
        history: list[dict[str, Any]] = []
        detail_parts: list[str] = []
        modifications = 0
        executed_rounds = 0
        round_idx = 0
        last_poem_key = tuple(current_poem)
        no_progress_streak = 0

        while True:
            round_idx += 1
            round_num = start_round + round_idx
            if on_stream:
                on_stream("")
                _fire_stream(on_stream, f"[第{round_num}轮] 思考中...")

            self._check_and_compress(
                messages, description, current_poem, template, template_obj
            )
            response = self.client.chat(messages, tools=WRITER_TOOLS)

            if not response["tool_calls"]:
                messages.append(LLMClient.assistant_to_message(response))
                messages.append(
                    {
                        "role": "user",
                        "content": "请调用工具来优化诗句。你可以使用 search_words、refine_line、rewrite 或 submit。",
                    }
                )
                continue

            executed_rounds += 1
            if on_stream:
                _fire_stream(
                    on_stream,
                    f"[第{round_num}轮] 思考完成"
                    + (
                        f" → 调用工具: {response['tool_calls'][0]['name']}"
                        if response.get("tool_calls")
                        else ""
                    ),
                )

            results_by_id: dict[str, dict[str, Any]] = {}
            for tool_call in response["tool_calls"]:
                name = str(tool_call["name"])
                args = tool_call["arguments"]

                if name == "submit":
                    if modifications < 1:
                        detail_parts.append(
                            f"[第{round_num}轮] submit: 拒绝 - 尚未进行任何修改，必须先调用 refine_line 或 rewrite"
                        )
                        results_by_id[tool_call["id"]] = {
                            "error": "不允许直接提交。你必须至少调用一次 refine_line 或 rewrite 成功修改诗句后，才能调用 submit。"
                        }
                        history.append(
                            {
                                "tool": "submit",
                                "arguments": args,
                                "result": "rejected_no_changes",
                            }
                        )
                        continue
                    submitted = True
                    history.append({"tool": "submit", "result": "submitted"})
                    detail_parts.append(f"[第{round_num}轮] submit: 提交定稿")
                    break

                result: dict[str, Any] | None = None
                if name == "search_words":
                    result = execute_search_words(template, args)
                    word_count_result = len(result.get("words", []))
                    detail_parts.append(
                        f"[第{round_num}轮] search_words({args.get('meaning', '')}): 找到{word_count_result}个候选词"
                    )
                elif name == "refine_line":
                    result = execute_refine_line(current_poem, template, args)
                    if "poem" in result:
                        current_poem = result["poem"]
                        modifications += 1
                        full_result = self.validator.validate(
                            current_poem, template, template_obj
                        )
                        if not full_result.passed:
                            result["validation_errors"] = full_result.errors
                    detail = f"[第{round_num}轮] refine_line(行{args.get('line')}, '{args.get('new_text', '')}')"
                    if "error" in result:
                        detail += f": 失败 - {result['error']}"
                    else:
                        detail += ": 成功"
                        if "validation_errors" in result:
                            detail += f" (格律问题: {result['validation_errors']})"
                    detail_parts.append(detail)
                elif name == "rewrite":
                    result = self._handle_rewrite(
                        description,
                        current_poem,
                        template,
                        template_obj,
                        args,
                        on_stream=on_stream,
                    )
                    if "poem" in result:
                        current_poem = result["poem"]
                        modifications += 1
                    detail = f"[第{round_num}轮] rewrite({args.get('instruction', '')})"
                    if "poem" in result:
                        detail += ": 重写完成"
                    detail_parts.append(detail)

                if result is not None:
                    results_by_id[tool_call["id"]] = result
                    history.append({"tool": name, "arguments": args, "result": result})

                    if "poem" in result:
                        detail_parts.append("当前诗稿:\n" + "\n".join(current_poem))

                    if on_step:
                        on_step(
                            {
                                "poem": list(current_poem),
                                "last_tool": name,
                                "last_result": result,
                                "detail": "\n".join(detail_parts)
                                if detail_parts
                                else "",
                                "stream_text": "",
                            }
                        )

            if submitted:
                break

            messages.append(LLMClient.assistant_to_message(response))
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(
                        results_by_id.get(tc["id"], {"error": "工具未执行"}),
                        ensure_ascii=False,
                    ),
                }
                for tc in response["tool_calls"]
            )

            # 空转引导: 连续多轮未成功修改也未提交时，提示 AI 继续推进(不中断循环)
            changed = tuple(current_poem) != last_poem_key
            last_poem_key = tuple(current_poem)
            no_progress_streak = no_progress_streak + 1 if not changed else 0
            if no_progress_streak >= 3:
                no_progress_streak = 0
                messages.append(
                    {
                        "role": "user",
                        "content": "你已连续多轮未成功修改诗句或提交。请调用 refine_line 或 rewrite 修改诗句；若对当前诗稿满意，请直接调用 submit 提交。",
                    }
                )

        return (
            current_poem,
            submitted,
            history,
            "\n".join(detail_parts) if detail_parts else "",
            executed_rounds,
        )

    def _handle_rewrite(
        self,
        description: str,
        poem: list[str],
        template: dict[str, Any],
        template_obj: object = None,
        args: dict[str, Any] | None = None,
        on_stream: ChunkCallback = None,
    ) -> dict[str, Any]:
        """执行整体重写（无尝试次数上限，通过格律校验即返回）。

        Args:
            description: 主题描述。
            poem: 当前诗稿。
            template: 模板字典。
            template_obj: 模板对象。
            args: 工具参数（instruction）。
            on_stream: 流式回调。

        Returns:
            {"poem": 新诗稿} 或 {"poem": ..., "note": 提示}。
        """
        if args is None:
            args = {}
        instruction = str(args.get("instruction", ""))
        lines = int(template.get("lines", 4))
        syllables_per_line = template.get("syllables_per_line", [])

        if template_obj is not None and hasattr(template_obj, "describe"):
            meter_desc = template_obj.describe()
        else:
            meter_desc = f"行数: {lines}\n每行音节数: {syllables_per_line}"

        sys_prompt = (
            f"""请根据指令重写全诗。

【主题描述】
{description}

【格律要求】
{meter_desc}

【重写指令】
{instruction}

【当前诗稿】
"""
            + "\n".join(f"[{i}] {line}" for i, line in enumerate(poem))
            + """

请直接输出重写后的全诗，每行一句，不要加序号或其他文字。"""
        )

        messages: list[Message] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "请按指令重写全诗。"},
        ]

        new_poem = poem
        attempt = 0
        while True:
            attempt += 1
            if on_stream and attempt == 1:
                _fire_stream(on_stream, "[rewrite] 生成中...")
                response = self.client.chat_stream(
                    messages,
                    on_chunk=lambda text: _fire_stream(on_stream, text),
                )
            else:
                response = self.client.chat(messages)
            text = str(response["content"]).strip()
            new_poem = [line.strip() for line in text.split("\n") if line.strip()]

            if len(new_poem) != lines:
                messages.append(LLMClient.assistant_to_message(response))
                messages.append(
                    {
                        "role": "user",
                        "content": f"输出行数为{len(new_poem)}，需要恰好{lines}行。",
                    }
                )
                continue

            full_result = self.validator.validate(new_poem, template, template_obj)
            if full_result.passed:
                return {"poem": new_poem}

            messages.append(LLMClient.assistant_to_message(response))
            messages.append(
                {
                    "role": "user",
                    "content": "格律校验未通过:\n"
                    + "\n".join(full_result.errors)
                    + "\n请修正。",
                }
            )
