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
        f"- Language: {language}\n- Lines: {lines}\n"
        "- Syllables per line: "
        f"{', '.join(format_count(c) for c in syllables_per_line)}"
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
        f"You are an AI poet skilled in {language} poetry.\n"
        "Based on the topic description above, write a poem that follows the "
        "meter requirements below.\n"
        "\n"
        "[Meter requirements]\n"
        f"{constraints_desc}\n"
        "\n"
        "When the poem is done, call the submit tool to submit the draft. The "
        "system automatically checks the line and syllable counts; if the check "
        "fails it returns the specific errors, and you must adjust the poem "
        "accordingly and submit it again.\n"
        "\n"
        "You have the following tool available: submit (submit the poem draft)."
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
        "Polish the poem draft above line by line.",
        "",
        "[Meter requirements]",
        constraints_desc,
        "",
    ]
    if feedback:
        parts.extend(["[Feedback / suggestions]", feedback, ""])
    parts.extend(
        [
            (
                "You have the following tools available: search_words (search "
                "candidate words), modify (revise the poem draft: a line, the "
                "title, or the punctuation), submit (submit the final draft; it "
                "can replace the whole poem and set punctuation)."
            ),
            (
                "The modify_type of modify is line/title/punctuation: for line, "
                "provide the line number line and the new line text content; for "
                "punctuation, content is a punctuation list whose length must "
                "equal the meter line count."
            ),
            (
                "After every modify call that revises a line, the system "
                "automatically validates the meter and returns the specific "
                "errors on failure."
            ),
            "When you are satisfied with the whole poem, call submit.",
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
        poem_text = "\n".join(poem) if poem else "(none)"
        compress_prompt = (
            "Compress the conversation state below into a structured summary, "
            "keeping all key information needed to continue the work.\n"
            "\n"
            "[Current poem draft]\n"
            f"{poem_text}\n"
            "\n"
            "[Meter constraints]\n"
            f"{constraints_desc}\n"
            "\n"
            "Output the summary in the following format:\n"
            "[Goal] the core goal of the current task\n"
            "[Key details] key information, meter constraints, important "
            "decisions already made\n"
            "[Working state]\n"
            "  Done: ...\n"
            "  In progress: ...\n"
            "  Blocked: ...\n"
            "[Next action] the concrete next step you suggest"
        )
        summary_response = self.client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a poetry-writing assistant; compress the "
                        "conversation state."
                    ),
                },
                {"role": "user", "content": compress_prompt},
            ]
        )
        summary_text = str(summary_response.get("content", "")).strip()
        messages.clear()
        messages.append(
            {
                "role": "system",
                "content": (
                    "Below is the compressed summary of the previous "
                    "conversation; the new conversation continues from here:\n\n"
                    f"{summary_text}\n\n"
                    "Continue the work based on the summary above. The current "
                    "poem draft is as follows:"
                ),
            }
        )
        messages.append(
            {"role": "user", "content": f"Current poem draft:\n{poem_text}"}
        )

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
                    "You are a poetry-writing assistant. Given the user's topic, "
                    "write a modern-prose description of no more than 100 "
                    "characters, covering the imagery, emotion, and content "
                    "outline. Output the description text directly, with no "
                    "prefix."
                ),
            }
        )
        messages.append({"role": "user", "content": f"Topic: {topic}"})
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
        messages.append({"role": "user", "content": "Please write the poem draft."})

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
                        "content": (
                            f"The output has {len(poem)} lines, but {lines} lines "
                            "are expected. Please output the poem again and call "
                            "submit."
                        ),
                    }
                )
                continue

            count_result = self.validator.validate_count_only(poem, template)
            if count_result.passed:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The poem draft passed validation; call the submit "
                            "tool to submit it."
                        ),
                    }
                )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": "Meter validation failed:\n"
                        + "\n".join(count_result.errors)
                        + "\nFix the poem, then output it again and call submit.",
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
                    "Begin the line-polishing pass. First use search_words to "
                    "search for candidate words, then use modify to revise lines, "
                    "the title, or the punctuation; when satisfied, call submit."
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
                        "content": (
                            "Please call a tool to polish the poem. You can use "
                            "search_words, modify, or submit."
                        ),
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
                        "content": (
                            "You have gone several rounds without successfully "
                            "revising the poem or submitting. Call modify to "
                            "revise the poem; if you are satisfied with the "
                            "current draft, call submit directly."
                        ),
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
