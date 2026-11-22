# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Writer AI: description generation, first draft, and ReAct line-polishing loop.

The polishing loop has no round limit: the AI repeatedly calls
search_words/modify to revise lines, the title, or punctuation (a full meter
validation runs after every change) until it calls submit; submit can replace
the whole poem via poem and set punctuation via punctuation, and it is also
validated in full before being accepted (a rejection returns the errors to the
model for further edits). After several rounds without progress, a guiding hint
is injected without interrupting the loop.

When the conversation token count exceeds COMPRESS_THRESHOLD, the history is
compressed automatically and a new conversation is started, keeping a structured
summary (goal / key details / working state / next action) and the current draft.
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
    """Parse and validate the punctuation list.

    Args:
        raw: Raw punctuation argument (None / list[str]).
        lines: Number of metrical lines.

    Returns:
        (punctuation list, error); (None, None) when left empty, (None, error)
        when invalid.

    """
    if raw is None or raw == []:
        return None, None
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None, "Punctuation must be a list of strings"
    if len(raw) != lines:
        return None, f"Expected {lines} punctuation marks, got {len(raw)}"
    return list(raw), None


def _fire_stream(cb: ChunkCallback, text: str) -> None:
    """Safely fire the streaming callback (swallow internal exceptions).

    A frontend stream-callback failure must not interrupt generation.

    Args:
        cb: Callback function.
        text: Callback text.

    """
    if cb:
        try:
            cb(text)
        except Exception:  # noqa: S110, BLE001 - swallow callback errors
            pass


def _get_constraints_desc(template: dict[str, Any], template_obj: object = None) -> str:
    """Return the meter-constraint description text.

    Args:
        template: Template dictionary.
        template_obj: Template object.

    Returns:
        Meter description text.

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
    """Build the Step 2 first-draft system prompt.

    Args:
        language: Language code.
        constraints_desc: Meter-constraint description.

    Returns:
        System prompt text.

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
    """Build the Step 3 polishing-loop system prompt.

    Args:
        constraints_desc: Meter-constraint description.
        feedback: User / checker AI feedback.

    Returns:
        System prompt text.

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
    """Extract the latest poem lines from the conversation history.

    Scans the content of assistant messages for consecutive non-empty lines
    that form the poem.

    Args:
        messages: Conversation message list.

    Returns:
        Extracted poem lines.

    """
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            text = str(msg["content"])
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if lines:
                return lines
    return []


class WriterAI:
    """Writer AI: neural layer of the four-step pipeline (desc/draft/polish)."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the writer AI.

        Args:
            config: {"base_url", "api_key", "model"}.

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
        """Compress the conversation history into a structured LLM summary.

        The summary contains the goal, key details, working state, next action,
        and the current poem.

        Args:
            messages: Message list to compress (modified in place).
            description: Topic description.
            poem: Current poem.
            template: Template dictionary.
            template_obj: Template object.

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
        """Check the token count and compress the history once above the threshold.

        Args:
            messages: Message list.
            description: Topic description.
            poem: Current poem.
            template: Template dictionary.
            template_obj: Template object.

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
        """Generate a modern-prose description of the topic (Step 1).

        Args:
            topic: User topic.
            messages: Shared conversation message list (appended to).
            on_stream: Streaming callback.

        Returns:
            Description text.

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
        """Generate the first draft (Step 2, via submit tool, no attempt cap).

        Args:
            description: Topic description.
            template: Template dictionary.
            messages: Shared conversation message list (appended to).
            template_obj: Template object.
            on_stream: Streaming callback.

        Returns:
            (poem, title, punctuation list, log text).

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
                _fire_stream(on_stream, "[draft] thinking...")
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
                                # The AI left the poem out of content; parse history
                                poem = _extract_poem_from_messages(messages)
                        punct, punct_err = _parse_punctuation(
                            args.get("punctuation"), lines
                        )

                        if not title:
                            result: dict[str, Any] = {
                                "error": "Title must not be empty; provide a poem title"
                            }
                        elif punct_err:
                            result = {"error": punct_err}
                        elif len(poem) != lines:
                            result = {
                                "error": (
                                    f"Output has {len(poem)} lines, expected {lines}"
                                )
                            }
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
                                _fire_stream(on_stream, "[draft] done")
                            return poem, title, punctuation, "\n\n".join(detail_parts)
                        continue

                continue

            # The AI did not call submit; parse the text content
            text = str(response["content"]).strip()
            detail_parts.append(f"generated:\n{text}")
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
        """ReAct polishing loop (Step 3, no round limit, until meter checks pass).

        A full meter validation runs immediately after every modify; submit is
        likewise validated in full first and the draft is accepted only when it
        passes, otherwise the errors are returned to the model for further edits.
        submit can replace the whole poem via poem and set punctuation via
        punctuation.

        Args:
            description: Topic description.
            poem: Current poem.
            template: Template dictionary.
            messages: Shared conversation message list (appended to).
            template_obj: Template object.
            feedback: User / checker AI feedback.
            on_step: Callback after each tool execution.
            on_stream: Streaming callback.
            start_round: Starting round number (for resumed runs).
            title: Current title.
            punctuation: Current punctuation.

        Returns:
            (poem, tool history, log, executed rounds, title, punctuation).

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
                _fire_stream(on_stream, f"[round {round_num}] thinking...")

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
                    f"[round {round_num}] thinking done"
                    + (
                        f" → tool call: {response['tool_calls'][0]['name']}"
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
                    # Optional whole-poem replacement (use submit for full edits).
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
                            f"[round {round_num}] submit: rejected - {punct_err}"
                        )
                    else:
                        if punct is not None:
                            current_punctuation = punct
                        # submit must pass full meter validation (same as the
                        # review after every change), otherwise reject and return
                        # the concrete errors to the model for more edits.
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
                                f"[round {round_num}] submit: final draft accepted "
                                "(full meter validation passed)"
                            )
                            submit_called = True
                            break
                        result = {"error": submit_result.errors}
                        detail_parts.append(
                            f"[round {round_num}] submit: full meter validation "
                            f"failed, rejected - {submit_result.errors}"
                        )
                elif name == "search_words":
                    result = execute_search_words(template, args)
                    word_count_result = len(result.get("words", []))
                    detail_parts.append(
                        f"[round {round_num}] search_words("
                        f"{args.get('query', '')}): found "
                        f"{word_count_result} candidate words"
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
                        f"[round {round_num}] modify({args.get('modify_type')}"
                        + (
                            f", line {args.get('line')}"
                            if args.get("modify_type") == "line"
                            else ""
                        )
                        + ")"
                    )
                    if "error" in result:
                        detail += f": failed - {result['error']}"
                    else:
                        detail += ": succeeded"
                        if "validation_errors" in result:
                            detail += f" (meter issues: {result['validation_errors']})"
                    detail_parts.append(detail)

                if result is not None:
                    results_by_id[tool_call["id"]] = result
                    history.append({"tool": name, "arguments": args, "result": result})

                    if "poem" in result:
                        detail_parts.append("current poem:\n" + "\n".join(current_poem))

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
                    detail_parts.append(
                        f"[round {round_num}] meter validation passed; polishing done"
                    )
                    break

            messages.append(LLMClient.assistant_to_message(response))
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(
                        results_by_id.get(tc["id"], {"error": "Tool was not executed"}),
                        ensure_ascii=False,
                    ),
                }
                for tc in response["tool_calls"]
            )

            # Idle-loop nudge: after several rounds without a successful edit or
            # submit, prompt the AI to keep going (without breaking the loop)
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
