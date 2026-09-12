# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""编写 AI：描述生成、初稿生成、ReAct 炼句循环。.

炼句循环无轮数上限：AI 反复调用 search_words/modify
修改诗句、标题或标点（每次修改后自动跑全部格律校验），直到调用 submit
提交；submit 可通过 poem 整首替换、通过 punctuation 设置标点，提交时
同样先做全量格律校验，通过后才接受定稿（拒绝则把错误返回模型继续修改）。
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
from ..tools.modify import execute_modify
from ..tools.search_words import execute_search_words
from .base import LLMClient, Message

COMPRESS_THRESHOLD = 180_000

ChunkCallback = Callable[[str], None] | None
StepCallback = Callable[[dict[str, Any]], None] | None
DraftResult = tuple[list[str], str, list[str], str]
RefineResult = tuple[list[str], list[dict[str, Any]], str, int, str, list[str]]


def _parse_punctuation(raw: Any, lines: int) -> tuple[list[str] | None, str | None]:
    """解析并校验标点列表。.

    Args:
        raw: 原始标点参数（None / list[str]）。
        lines: 格律行数。

    Returns:
        (标点列表, 错误)；留空返回 (None, None)，非法返回 (None, 错误)。

    """
    if raw is None or raw == []:
        return None, None
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None, "标点必须是字符串列表"
    if len(raw) != lines:
        return None, f"标点数量应为 {lines} 个，实际 {len(raw)} 个"
    return list(raw), None


def _fire_stream(cb: ChunkCallback, text: str) -> None:
    """安全触发流式回调（吞掉回调内部异常）。.

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
    """获取格律约束描述文本。.

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
    """构造 Step 2 初稿生成的系统提示。.

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
    """构造 Step 3 炼句循环的系统提示。.

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
                "你有以下工具可用: search_words(搜候选词), modify(修改诗稿："
                "改某行/标题/标点), submit(提交定稿，可整首替换并设置标点)。"
            ),
            (
                "modify 的 modify_type 取 line/title/punctuation：line 需给出"
                "行号 line 与该行新文本 content；punctuation 的 content 为标点"
                "列表，长度须等于格律行数。"
            ),
            ("每次调用 modify 修改诗句后，系统会自动校验格律，不通过会返回具体错误。"),
            "当你对全诗满意时，调用 submit 提交。",
        ]
    )
    return "\n".join(parts)


def _extract_poem_from_messages(messages: list[Message]) -> list[str]:
    """从对话历史中提取最近的诗稿行。.

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
    """编写 AI：四步流水线的神经层（描述/初稿/炼句）。."""

    def __init__(self, config: dict[str, Any]):
        """初始化编写 AI。.

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
        """压缩对话历史：用 LLM 生成结构化摘要，替换当前消息列表。.

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
        """检查 token 数，超过阈值时自动压缩对话历史。.

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
    ) -> str:
        """生成主题的现代文描述（Step 1）。.

        Args:
            topic: 用户主题。
            messages: 共享对话消息列表（会被追加）。
            on_stream: 流式回调。

        Returns:
            描述文本。

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
        return desc

    def generate_draft(
        self,
        description: str,
        template: dict[str, Any],
        messages: list[Message],
        template_obj: object = None,
        on_stream: ChunkCallback = None,
    ) -> DraftResult:
        """生成初稿（Step 2，通过 submit 工具提交，无尝试次数上限）。.

        Args:
            description: 主题描述。
            template: 模板字典。
            messages: 共享对话消息列表（会被追加）。
            template_obj: 模板对象。
            on_stream: 流式回调。

        Returns:
            (诗稿, 标题, 标点列表, 日志文本)。

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
        punctuation: list[str] = []
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
                        args = tc["arguments"]
                        title = str(args.get("title", "")).strip()
                        provided = args.get("poem")
                        if isinstance(provided, list) and provided:
                            poem = [str(ln).strip() for ln in provided]
                        else:
                            text = str(response.get("content", "")).strip()
                            if text:
                                poem = [
                                    ln.strip() for ln in text.split("\n") if ln.strip()
                                ]
                            else:
                                # AI 没有在 content 中输出诗稿，从历史中解析
                                poem = _extract_poem_from_messages(messages)
                        punct, punct_err = _parse_punctuation(
                            args.get("punctuation"), lines
                        )

                        if not title:
                            result: dict[str, Any] = {
                                "error": "标题不能为空，请提供诗稿标题"
                            }
                        elif punct_err:
                            result = {"error": punct_err}
                        elif len(poem) != lines:
                            result = {"error": f"输出行数为{len(poem)}，期望{lines}行"}
                        else:
                            count_result = self.validator.validate_count_only(
                                poem, template
                            )
                            if count_result.passed:
                                punctuation = punct or []
                                result = {
                                    "status": "passed",
                                    "poem": poem,
                                    "title": title,
                                    "punctuation": punctuation,
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
                            return poem, title, punctuation, "\n\n".join(detail_parts)
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
        title: str = "",
        punctuation: list[str] | None = None,
    ) -> RefineResult:
        """ReAct 炼句循环（Step 3，无轮数上限，直到格律校验通过）。.

        每次 modify 修改诗句后都会立即执行全量格律校验；调用 submit 时
        同样先做全量校验，通过才接受定稿，否则把错误返回给模型继续修改。
        submit 可通过 poem 整首替换、通过 punctuation 设置标点。

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
            title: 当前标题。
            punctuation: 当前标点。

        Returns:
            (诗稿, 工具历史, 日志, 执行轮数, 标题, 标点)。

        """
        current_poem = list(poem)
        current_title = title
        current_punctuation = list(punctuation or [])
        lines = int(template.get("lines", len(current_poem)))
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
                    "请开始炼句优化。先用 search_words 搜候选词，然后用"
                    " modify 修改诗句、标题或标点，满意后调用 submit 提交。"
                ),
            }
        )

        history: list[dict[str, Any]] = []
        detail_parts: list[str] = []
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
                        "content": "请调用工具来优化诗句。你可以使用 search_words、modify 或 submit。",
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
            poem_changed = False
            submit_called = False
            for tool_call in response["tool_calls"]:
                name = str(tool_call["name"])
                args = tool_call["arguments"]

                result: dict[str, Any] | None = None
                if name == "submit":
                    # 可选整首替换（全量修改用 submit 即可）。
                    provided = args.get("poem")
                    if isinstance(provided, list) and provided:
                        current_poem = [str(ln).strip() for ln in provided]
                    new_title = str(args.get("title", "")).strip()
                    if new_title:
                        current_title = new_title
                    punct, punct_err = _parse_punctuation(
                        args.get("punctuation"), lines
                    )
                    if punct_err:
                        result = {"error": punct_err}
                        detail_parts.append(
                            f"[第{round_num}轮] submit: 拒绝提交 - {punct_err}"
                        )
                    else:
                        if punct is not None:
                            current_punctuation = punct
                        # 提交前必须通过全量格律校验（与每次修改后的全量审查一致），
                        # 否则拒绝并把具体错误返回给模型继续修改。
                        submit_result = self.validator.validate(
                            current_poem, template, template_obj
                        )
                        if submit_result.passed:
                            history.append(
                                {
                                    "tool": "submit",
                                    "arguments": args,
                                    "result": "submitted",
                                }
                            )
                            detail_parts.append(
                                f"[第{round_num}轮] submit: 提交定稿 (全量格律校验通过)"
                            )
                            submit_called = True
                            break
                        result = {"error": submit_result.errors}
                        detail_parts.append(
                            f"[第{round_num}轮] submit: 全量格律校验未通过，拒绝提交 - {submit_result.errors}"
                        )
                elif name == "search_words":
                    result = execute_search_words(template, args)
                    word_count_result = len(result.get("words", []))
                    detail_parts.append(
                        f"[第{round_num}轮] search_words({args.get('query', '')}): 找到{word_count_result}个候选词"
                    )
                elif name == "modify":
                    result = execute_modify(
                        current_poem,
                        template,
                        args,
                        title=current_title,
                        punctuation=current_punctuation,
                    )
                    if "poem" in result:
                        current_poem = result["poem"]
                        poem_changed = True
                        full_result = self.validator.validate(
                            current_poem, template, template_obj
                        )
                        if not full_result.passed:
                            result["validation_errors"] = full_result.errors
                    elif "title" in result:
                        current_title = result["title"]
                    elif "punctuation" in result:
                        current_punctuation = result["punctuation"]
                    detail = (
                        f"[第{round_num}轮] modify({args.get('modify_type')}"
                        + (
                            f", 行{args.get('line')}"
                            if args.get("modify_type") == "line"
                            else ""
                        )
                        + ")"
                    )
                    if "error" in result:
                        detail += f": 失败 - {result['error']}"
                    else:
                        detail += ": 成功"
                        if "validation_errors" in result:
                            detail += f" (格律问题: {result['validation_errors']})"
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
                                "title": current_title,
                                "punctuation": list(current_punctuation),
                                "last_tool": name,
                                "last_result": result,
                                "detail": "\n".join(detail_parts)
                                if detail_parts
                                else "",
                                "stream_text": "",
                            }
                        )

            if submit_called:
                break

            if poem_changed:
                check = self.validator.validate(current_poem, template, template_obj)
                if check.passed:
                    detail_parts.append(f"[第{round_num}轮] 格律校验通过，优化结束")
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
                        "content": "你已连续多轮未成功修改诗句或提交。请调用 modify 修改诗句；若对当前诗稿满意，请直接调用 submit 提交。",
                    }
                )

        return (
            current_poem,
            history,
            "\n".join(detail_parts) if detail_parts else "",
            executed_rounds,
            current_title,
            current_punctuation,
        )
