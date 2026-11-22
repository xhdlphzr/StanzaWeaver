# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Four-step generation pipeline and rejection loop.

Step 1 generates the description; Step 2 drafts the poem (including the title;
syllable checks only); Step 3 runs the line-refinement loop (ReAct tools, with a
full meter validation after every change); Step 4 sends the poem to the checker
AI for a final meaning review. A failed final review sends the poem back to
Step 3 automatically (no round limit; it keeps rejecting until the final review
passes). A user "reject" feedback resumes the run through
``continue_with_feedback``.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..agents.base import Message
from ..agents.checker_ai import CheckerAI
from ..agents.writer_ai import WriterAI
from ..config import get_config
from ..prosody.meter_validator import MeterValidator
from ..templates import get as get_template

ProgressCallback = Callable[[dict[str, Any]], None] | None


@dataclass
class PipelineState:
    """Complete state of one generation session (serializable and resumable)."""

    topic: str = ""
    template_key: str = ""
    template: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    draft: list[str] = field(default_factory=list)
    refine_rounds: int = 0
    refine_history: list[dict[str, Any]] = field(default_factory=list)
    checker_pass: bool = False
    checker_suggestions: str = ""
    user_feedback: str = ""
    current_step: int = 0
    final_poem: list[str] = field(default_factory=list)
    step_details: list[dict[str, Any]] = field(default_factory=list)
    last_tool: str = ""
    last_tool_result: str = ""
    stream_text: str = ""
    current_detail_step: int = 0
    current_detail: str = ""
    messages: list[Message] = field(default_factory=list)
    title: str = ""
    punctuation: list[str] = field(default_factory=list)
    formatted_poem: str = ""


class PoetryPipeline:
    """Generation pipeline: orchestrate writer, checker and symbolic validation."""

    def __init__(
        self,
        writer_config: dict[str, Any] | None = None,
        checker_config: dict[str, Any] | None = None,
    ):
        """Initialize the pipeline.

        Args:
            writer_config: Writer AI config (defaults to the global config).
            checker_config: Checker AI config (defaults to the global config).

        """
        config = get_config()
        self.writer_config = writer_config or config.writer
        self.checker_config = checker_config or config.checker
        self.writer: WriterAI | None = None
        self.checker: CheckerAI | None = None
        self.validator = MeterValidator()
        self._on_progress: ProgressCallback = None
        self._template_obj: object = None
        self._detail_seq = 0

    def _append_detail(self, state: PipelineState, **kwargs: Any) -> None:
        """Append one step-detail entry (auto-numbered ``seq`` for frontend dedup).

        Args:
            state: Pipeline state.
            **kwargs: Step-detail fields (step/title/content/rounds, etc.).

        """
        kwargs["seq"] = self._detail_seq
        self._detail_seq += 1
        state.step_details.append(kwargs)

    def _init_agents(self) -> None:
        """Initialize the writer/checker AI agents lazily."""
        if self.writer is None:
            self.writer = WriterAI(self.writer_config)
        if self.checker is None:
            self.checker = CheckerAI(self.checker_config)

    def _get_writer(self) -> WriterAI:
        """Get the writer AI (initializing it if needed).

        Returns:
            WriterAI instance.

        """
        self._init_agents()
        assert self.writer is not None
        return self.writer

    def _get_checker(self) -> CheckerAI:
        """Get the checker AI (initializing it if needed).

        Returns:
            CheckerAI instance.

        """
        self._init_agents()
        assert self.checker is not None
        return self.checker

    def _load_template(self, key: str) -> dict[str, Any]:
        """Load the template object and dictionary.

        Args:
            key: Template key.

        Returns:
            Template dictionary (``to_dict()``).

        """
        self._template_obj = get_template(key)
        return self._template_obj.to_dict()

    def _format_current(self, state: PipelineState) -> str:
        """Format the current draft/title/punctuation for live display.

        Args:
            state: Pipeline state.

        Returns:
            Formatted text; empty string when there is no draft.

        """
        if not state.draft:
            return ""
        if self._template_obj is not None and hasattr(
            self._template_obj, "format_poem"
        ):
            text = str(
                self._template_obj.format_poem(
                    [state.title, *state.draft], state.punctuation or None
                )
            )
            return text if state.title else text.lstrip("\n")
        lines = ([state.title] if state.title else []) + list(state.draft)
        return "\n".join(lines)

    def _report(self, state: PipelineState) -> None:
        """Push a progress event to the frontend.

        Args:
            state: Pipeline state.

        """
        if self._on_progress:
            self._on_progress(
                {
                    "step": state.current_step,
                    "description": state.description,
                    "draft": state.draft,
                    "title": state.title,
                    "formatted_poem": self._format_current(state),
                    "language": str(state.template.get("language", "")),
                    "centered": bool(state.template.get("centered", True)),
                    "refine_rounds": state.refine_rounds,
                    "checker_pass": state.checker_pass,
                    "checker_suggestions": state.checker_suggestions,
                    "step_details": state.step_details,
                    "last_tool": state.last_tool,
                    "last_tool_result": state.last_tool_result,
                    "stream_text": state.stream_text,
                    "current_detail_step": state.current_detail_step,
                    "current_detail": state.current_detail,
                }
            )

    def run(
        self,
        topic: str,
        template_key: str,
        user_feedback: str = "",
        existing_state: PipelineState | None = None,
        on_progress: ProgressCallback = None,
    ) -> PipelineState:
        """Run the full flow (or resume with feedback).

        Args:
            topic: Topic.
            template_key: Template key.
            user_feedback: User feedback (provided when resuming).
            existing_state: Existing state (provided when resuming).
            on_progress: Progress callback.

        Returns:
            Final pipeline state.

        """
        self._on_progress = on_progress
        self._init_agents()

        if existing_state and user_feedback:
            state = existing_state
            state.user_feedback = user_feedback
            self._detail_seq = len(state.step_details)
            self._load_template(state.template_key)
            messages = list(state.messages)
            self._run_refine_loop(state, messages)
            state.messages = messages
            return state

        template_dict = self._load_template(template_key)
        state = PipelineState(
            topic=topic, template_key=template_key, template=template_dict
        )
        self._detail_seq = 0
        messages = []
        self._run_step1(state, messages)
        self._run_step2(state, messages)
        self._run_refine_loop(state, messages)
        state.messages = messages
        return state

    def _run_step1(self, state: PipelineState, messages: list[Message]) -> None:
        """Run Step 1 to generate a modern-language description (streamed).

        Args:
            state: Pipeline state (updates ``description`` in place).
            messages: Shared conversation messages (appended to).

        """
        state.current_step = 1
        state.stream_text = ""
        state.current_detail_step = 1
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str) -> None:
            """Handle one streamed text fragment during generation.

            Args:
                text: Text fragment pushed in this stream update.

            """
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        description = self._get_writer().generate_description(
            state.topic, messages, on_stream=on_stream
        )
        state.description = description
        state.stream_text = ""
        state.current_detail = ""
        self._append_detail(
            state,
            step=1,
            title="Step 1: Generate description",
            content=description,
        )
        self._report(state)

    def _run_step2(self, state: PipelineState, messages: list[Message]) -> None:
        """Run Step 2 to generate the first draft.

        The draft is submitted through the submit tool, which also returns the
        title and punctuation.

        Args:
            state: Pipeline state (updates draft/title/punctuation in place).
            messages: Shared conversation messages (appended to).

        """
        state.current_step = 2
        state.stream_text = ""
        state.current_detail_step = 2
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str) -> None:
            """Handle one streamed text fragment during generation.

            Args:
                text: Text fragment pushed in this stream update.

            """
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        draft, title, punctuation, detail = self._get_writer().generate_draft(
            state.description,
            state.template,
            messages,
            self._template_obj,
            on_stream=on_stream,
        )
        state.draft = draft
        state.title = title
        state.punctuation = punctuation
        state.stream_text = ""
        self._append_detail(
            state,
            step=2,
            title="Step 2: Generate first draft",
            content=detail,
        )
        self._report(state)

    def _run_refine_loop(self, state: PipelineState, messages: list[Message]) -> None:
        """Run the Step 3-4 rejection loop until the final review passes.

        Refinement itself (``writer.refine``) has no round limit; this outer loop
        keeps sending the draft back for refinement while the checker AI fails
        it, also without a limit.

        Args:
            state: Pipeline state (updates draft/title/punctuation/checker
                results in place).
            messages: Shared conversation messages (appended to).

        """
        checker_feedback = state.user_feedback

        while True:
            state.current_step = 3
            self._report(state)

            def on_step(step_info: dict[str, Any]) -> None:
                """Step progress callback: receive the info dict of one generation step.

                Args:
                    step_info: Step info with poem / last_tool / last_result /
                        detail / stream_text.

                """
                state.draft = list(step_info["poem"])
                state.title = str(step_info.get("title", state.title))
                state.punctuation = list(
                    step_info.get("punctuation", state.punctuation)
                )
                state.last_tool = str(step_info["last_tool"])
                state.last_tool_result = json_dumps_safe(
                    step_info.get("last_result", "")
                )
                state.current_detail_step = 3
                state.current_detail = str(step_info.get("detail", ""))
                state.stream_text = str(step_info.get("stream_text", state.stream_text))
                self._report(state)

            last_report_time: list[float] = [0.0]

            def on_stream(text: str, _t: list[float] = last_report_time) -> None:
                """Handle one streamed text fragment during generation.

                Args:
                    text: Text fragment pushed in this stream update.

                """
                # Bind _t through a default argument to the current iteration's
                # throttle container, preventing the closure from capturing the
                # loop variable by mistake
                now = time.monotonic()
                if now - _t[0] >= 0.25 or not text:
                    _t[0] = now
                    state.stream_text = text
                    state.last_tool = "_thinking"
                    state.last_tool_result = text
                    self._report(state)

            poem, history, detail, tool_rounds, title, punctuation = (
                self._get_writer().refine(
                    description=state.description,
                    poem=state.draft,
                    template=state.template,
                    messages=messages,
                    template_obj=self._template_obj,
                    feedback=checker_feedback,
                    on_step=on_step,
                    on_stream=on_stream,
                    start_round=state.refine_rounds,
                    title=state.title,
                    punctuation=state.punctuation,
                )
            )

            state.draft = poem
            state.title = title
            state.punctuation = punctuation
            state.refine_history = history
            state.refine_rounds += tool_rounds
            self._append_detail(
                state,
                step=3,
                title="Step 3: Refine lines",
                content=detail,
                rounds=state.refine_rounds,
            )
            state.current_detail = ""

            if tool_rounds < 1:
                state.checker_pass = False
                state.checker_suggestions = "No refinement rounds were executed"
                self._report(state)
                break

            state.current_step = 4
            state.stream_text = ""
            self._report(state)

            # Checker AI fallback: any failure becomes "not passed + suggestions".
            try:
                # The checker AI reviews only the user's original prompt and the
                # template rule description; the writer's derived description is
                # not passed in, so a second-hand summary cannot skew the review
                # baseline.
                result = self._get_checker().check(
                    poem=state.draft,
                    template=state.template,
                    user_prompt=state.topic,
                    user_feedback=state.user_feedback,
                )
                state.checker_pass = bool(result["pass"])
                state.checker_suggestions = str(result.get("suggestions", ""))
            except Exception as e:  # noqa: BLE001
                state.checker_pass = False
                state.checker_suggestions = f"Checker AI error: {e}"

            self._append_detail(
                state,
                step=4,
                title="Step 4: Checker AI final review",
                content=f"pass={state.checker_pass}\n{state.checker_suggestions}",
            )
            self._report(state)

            if state.checker_pass:
                state.final_poem = (
                    [state.title] + state.draft if state.title else list(state.draft)
                )
                state.formatted_poem = self._format_current(state)
                break

            checker_feedback = state.checker_suggestions

        if not state.checker_pass and not state.final_poem:
            state.final_poem = (
                [state.title] + state.draft if state.title else list(state.draft)
            )
            state.formatted_poem = self._format_current(state)

    def continue_with_feedback(
        self,
        state: PipelineState,
        user_feedback: str,
        on_progress: ProgressCallback = None,
    ) -> PipelineState:
        """Resume with user feedback (send the draft back to Step 3 for refinement).

        Args:
            state: Existing state.
            user_feedback: User feedback text.
            on_progress: Progress callback.

        Returns:
            State after resuming.

        """
        self._on_progress = on_progress
        return self.run(
            topic=state.topic,
            template_key=state.template_key,
            user_feedback=user_feedback,
            existing_state=state,
            on_progress=on_progress,
        )


def json_dumps_safe(obj: Any, default: str = "") -> str:
    """Serialize to JSON safely (fall back to ``str`` on failure).

    ``json.dumps`` fails with TypeError (not serializable), ValueError
    (circular reference), or RecursionError (nesting too deep).

    Args:
        obj: Any object.
        default: Fallback when serialization fails.

    Returns:
        JSON string.

    """
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError, ValueError, RecursionError:
        return str(obj)
