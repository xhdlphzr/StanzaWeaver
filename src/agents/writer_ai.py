"""编写 AI：描述生成、初稿生成、ReAct 炼句循环。

炼句循环无轮数上限：AI 反复调用 search_words/refine_line/rewrite
修改诗句（每次修改后自动跑全部格律校验），直到调用 submit 提交。
连续多轮无进展时注入引导提示（不中断循环）。
"""

import json
from collections.abc import Callable
from typing import Any

from ..prosody.meter_validator import MeterValidator
from ..templates import format_count
from ..tools import WRITER_TOOLS
from ..tools.refine_line import execute_refine_line
from ..tools.search_words import execute_search_words
from .base import LLMClient, Message

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


def _build_writer_system(
    description: str,
    poem: list[str],
    template: dict[str, Any],
    template_obj: object = None,
    feedback: str = "",
) -> str:
    """构造编写 AI 的系统提示（含完整格律描述与当前诗稿）。

    Args:
        description: 主题描述。
        poem: 当前诗稿。
        template: 模板字典。
        template_obj: 模板对象（提供 describe() 时用完整格律描述）。
        feedback: 用户/检查 AI 反馈。

    Returns:
        系统提示文本。
    """
    lines_spec = template.get("syllables_per_line", [])
    language = template.get("language", "zh")

    prompt_parts = [
        "你是一位精通多语言诗歌创作的AI诗人。",
        f"当前任务语言: {language}",
        "",
        "【诗歌主题描述】",
        description,
        "",
        "【格律要求】",
    ]
    if template_obj is not None and hasattr(template_obj, "describe"):
        prompt_parts.append(template_obj.describe())
    else:
        prompt_parts.append(f"共 {template.get('lines', len(lines_spec))} 行")
        constraints = template.get("syllable_constraints") or []
        for i, count in enumerate(lines_spec):
            line_constraints = constraints[i] if i < len(constraints) else []
            parts = [f"  第{i + 1}行: {format_count(count)}音节"]
            if line_constraints:
                constraint_strs = []
                for j, c in enumerate(line_constraints):
                    desc_parts = []
                    if c.get("onset"):
                        desc_parts.append(f"声母={c['onset']}")
                    if c.get("nucleus"):
                        desc_parts.append(f"韵母={c['nucleus']}")
                    if c.get("coda"):
                        desc_parts.append(f"韵尾={c['coda']}")
                    for k, v in c.get("attributes", {}).items():
                        if v:
                            desc_parts.append(f"{k}={v}")
                    if desc_parts:
                        constraint_strs.append(
                            f"    第{j + 1}位: {','.join(desc_parts)}"
                        )
                if constraint_strs:
                    parts.append("\n".join(constraint_strs))
            prompt_parts.append("  ".join(parts))

    prompt_parts.append("")
    prompt_parts.append("【当前诗稿】")
    for i, line in enumerate(poem):
        prompt_parts.append(f"  [{i}] {line}")
    prompt_parts.append("")

    if feedback:
        prompt_parts.append(f"【反馈/建议】\n{feedback}\n")

    prompt_parts.append(
        "你有以下工具可用: search_words(搜候选词), refine_line(重写某一行), rewrite(整体重写全诗), submit(提交定稿)。"
    )
    prompt_parts.append(
        "每次调用 refine_line 或 rewrite 后，系统会自动校验格律，不通过会返回具体错误，你需要根据错误调整。"
    )
    prompt_parts.append("当你对全诗满意时，调用 submit 提交。")

    return "\n".join(prompt_parts)


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

    def generate_description(
        self, topic: str, on_stream: ChunkCallback = None
    ) -> tuple[str, str]:
        """生成主题的现代文描述（Step 1）。

        Args:
            topic: 用户主题。
            on_stream: 流式回调。

        Returns:
            (描述文本, 日志文本)。
        """
        messages: list[Message] = [
            {
                "role": "system",
                "content": "你是一位诗歌创作助手。根据用户给出的主题，写一段100字以内的现代文描述，包含意象、情感、内容概要。直接输出描述文本，不要加任何前缀。",
            },
            {"role": "user", "content": f"主题: {topic}"},
        ]
        if on_stream:
            response = self.client.chat_stream(messages, on_chunk=on_stream)
        else:
            response = self.client.chat(messages)
        desc = str(response["content"]).strip()
        detail = f"{desc}"
        return desc, detail

    def generate_draft(
        self,
        description: str,
        template: dict[str, Any],
        template_obj: object = None,
        max_attempts: int = 5,
        on_stream: ChunkCallback = None,
    ) -> tuple[list[str], str]:
        """生成初稿（Step 2，仅校验行数与音节数，最多尝试 max_attempts 次）。

        Args:
            description: 主题描述。
            template: 模板字典。
            template_obj: 模板对象。
            max_attempts: 最大尝试次数。
            on_stream: 流式回调。

        Returns:
            (诗稿, 日志文本)。
        """
        language = str(template.get("language", "zh"))
        lines = int(template.get("lines", 4))
        syllables_per_line = template.get("syllables_per_line", [5] * lines)

        constraints_desc = ""
        if template_obj is not None and hasattr(template_obj, "describe"):
            constraints_desc = template_obj.describe()
        else:
            constraints_desc = (
                f"- 语言: {language}\n- 行数: {lines}\n"
                f"- 每行音节数: {', '.join(format_count(c) for c in syllables_per_line)}"
            )

        sys_prompt = f"""你是一位精通{language}诗歌创作的AI诗人。
请根据以下主题描述和格律要求，创作一首诗。

【主题描述】
{description}

【格律要求】
{constraints_desc}

请直接输出诗歌，每行一句，不要加序号、标题或其他任何文字。
只输出纯诗文本，每行用换行分隔。"""

        messages: list[Message] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "请按以上格律要求生成诗稿。"},
        ]

        detail_parts: list[str] = []
        poem: list[str] = []
        for attempt in range(max_attempts):
            if on_stream and attempt == 0:
                response = self.client.chat_stream(messages, on_chunk=on_stream)
            else:
                response = self.client.chat(messages)
            text = str(response["content"]).strip()
            detail_parts.append(f"尝试 {attempt + 1}:\n{text}")
            poem = [line.strip() for line in text.split("\n") if line.strip()]

            if len(poem) != lines:
                messages.append(LLMClient.assistant_to_message(response))
                messages.append(
                    {
                        "role": "user",
                        "content": f"输出行数为{len(poem)}行，期望{lines}行。请重新输出恰好{lines}行。",
                    }
                )
                continue

            result = self.validator.validate_count_only(poem, template)
            if result.passed:
                return poem, "\n\n".join(detail_parts)

            detail_parts.append(f"校验未通过: {'; '.join(result.errors)}")
            messages.append(LLMClient.assistant_to_message(response))
            messages.append(
                {
                    "role": "user",
                    "content": "格律校验未通过:\n"
                    + "\n".join(result.errors)
                    + "\n请修正后重新输出。",
                }
            )

        return poem, "\n\n".join(detail_parts)

    def refine(
        self,
        description: str,
        poem: list[str],
        template: dict[str, Any],
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
            template_obj: 模板对象。
            feedback: 用户/检查 AI 反馈。
            on_step: 每次工具执行后的回调。
            on_stream: 流式回调。
            start_round: 起始轮号（打回续轮用）。

        Returns:
            (诗稿, 是否提交, 工具历史, 日志, 执行轮数)。
        """
        current_poem = list(poem)
        system_prompt = _build_writer_system(
            description, current_poem, template, template_obj, feedback
        )

        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请开始炼句优化。先用 search_words 搜候选词，然后必须至少调用一次 refine_line 或 rewrite 修改诗句，才能调用 submit 提交。",
            },
        ]

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
                        full_result = self.validator.validate(
                            current_poem, template, template_obj
                        )
                        if not full_result.passed:
                            result["validation_errors"] = full_result.errors
                    detail = f"[第{round_num}轮] rewrite({args.get('instruction', '')})"
                    if "poem" in result:
                        detail += ": 重写完成"
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

            system_prompt = _build_writer_system(
                description, current_poem, template, template_obj, feedback
            )
            messages[0] = {"role": "system", "content": system_prompt}

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
        """执行整体重写（最多 3 次尝试，通过格律校验即返回）。

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
        for attempt in range(3):
            if on_stream and attempt == 0:
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

        return {"poem": new_poem, "note": "重写后格律可能不完全满足"}
