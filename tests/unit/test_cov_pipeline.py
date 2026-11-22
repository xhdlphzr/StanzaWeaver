# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests that fill missing line coverage in pipeline.py.

Use lightweight fake Writer/Checker agents (subclassing the real agents but
bypassing LLMClient, never touching the network) to trigger error and
boundary branches:

- ``CheckerAI.check`` raises: hit the except fallback.
- ``CheckerAI.check`` returns ``pass=False`` then ``pass=True``: assign the
  continue feedback.
- Unit-test ``json_dumps_safe``'s serialization error branches directly.
"""

from typing import Any

import pytest

from src.agents.checker_ai import CheckerAI
from src.agents.writer_ai import (
    ChunkCallback,
    RefineResult,
    StepCallback,
    WriterAI,
)
from src.pipeline.pipeline import (
    PipelineState,
    PoetryPipeline,
    json_dumps_safe,
)
from src.templates import get as get_template

RefinePlan = list[tuple[list[str], list[dict[str, Any]], str, int]]
CheckPlan = list[dict[str, Any] | Exception]


class _FakeWriter(WriterAI):
    """Fake WriterAI returning preset refine results, never uses LLMClient."""

    def __init__(self, refine_plan: RefinePlan) -> None:
        """Record the preset refine sequence; no real LLM client is created.

        Args:
            refine_plan: RefineResults returned in order; a call after the
                list is exhausted raises IndexError.

        """
        self._refine_plan: RefinePlan = list(refine_plan)
        self.generate_description_calls: int = 0
        self.generate_draft_calls: int = 0
        self.feedback_log: list[str] = []

    def generate_description(
        self,
        topic: str,
        messages: list[dict[str, Any]],
        on_stream: ChunkCallback = None,
    ) -> str:
        """Return a fixed description (Step 1).

        Args:
            topic: Topic (unused).
            messages: Shared message list (unused).
            on_stream: Streaming callback (unused).

        Returns:
            Description text.

        """
        self.generate_description_calls += 1
        return "现代文描述"

    def generate_draft(
        self,
        description: str,
        template: dict[str, Any],
        messages: list[dict[str, Any]],
        template_obj: Any = None,
        on_stream: ChunkCallback = None,
    ) -> tuple[list[str], str, list[str], str]:
        """Return a fixed draft (Step 2).

        Args:
            description: Topic description (unused).
            template: Template dict (unused).
            messages: Shared message list (unused).
            template_obj: Template object (unused).
            on_stream: Streaming callback (unused).

        Returns:
            (poem, title, punctuation, log text).

        """
        self.generate_draft_calls += 1
        return ["床前明月光", "疑是地上霜"], "测试标题", [], "初稿详情"

    def refine(
        self,
        description: str,
        poem: list[str],
        template: dict[str, Any],
        messages: list[dict[str, Any]],
        template_obj: Any = None,
        feedback: str = "",
        on_step: StepCallback = None,
        on_stream: ChunkCallback = None,
        start_round: int = 0,
        title: str = "",
        punctuation: list[str] | None = None,
    ) -> RefineResult:
        """Return one preset refine result and fire the on_step callback.

        Args:
            description: Topic description (unused).
            poem: Current poem (unused).
            template: Template dict (unused).
            messages: Shared message list (unused).
            template_obj: Template object (unused).
            feedback: Checker AI/user feedback (unused).
            on_step: Per-step callback.
            on_stream: Streaming callback (unused).
            start_round: Starting round number (unused).
            title: Current title (returned unchanged).
            punctuation: Current punctuation (returned unchanged).

        Returns:
            Preset RefineResult (title/punctuation come from the arguments).

        """
        self.feedback_log.append(feedback)
        result = self._refine_plan.pop(0)
        poem_out, _history, detail, _rounds = result
        if on_step is not None:
            on_step(
                {
                    "poem": poem_out,
                    "title": title,
                    "punctuation": list(punctuation or []),
                    "last_tool": "submit",
                    "last_result": {},
                    "detail": detail,
                    "stream_text": "",
                }
            )
        return poem_out, _history, detail, _rounds, title, list(punctuation or [])


class _FakeChecker(CheckerAI):
    """Fake CheckerAI returning preset results/exceptions, never LLMClient."""

    def __init__(self, check_results: CheckPlan) -> None:
        """Record the preset check sequence (may be exceptions) and calls.

        Args:
            check_results: Results returned in order; exception items are
                raised as-is.

        """
        self._check_results: CheckPlan = list(check_results)
        self.calls: list[dict[str, Any]] = []

    def check(
        self,
        poem: list[str],
        template: dict[str, Any],
        user_prompt: str = "",
        user_feedback: str = "",
    ) -> dict[str, Any]:
        """Return one preset final review result, or raise if preset.

        Args:
            poem: Poem lines.
            template: Template dict.
            user_prompt: Original user prompt (recorded for assertions).
            user_feedback: User feedback (recorded for assertions).

        Returns:
            Preset final review result dict.

        Raises:
            Any preset exception (to cover the except fallback branch).

        """
        self.calls.append(
            {
                "template": template,
                "user_prompt": user_prompt,
                "user_feedback": user_feedback,
            }
        )
        item = self._check_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_state() -> PipelineState:
    """Build a minimal state with a loaded template ready for refinement.

    Returns:
        PipelineState with only the fields the refine loop needs.

    """
    return PipelineState(
        topic="静夜思",
        template_key="zh_wujue",
        template={"lines": 4, "language": "zh", "syllables_per_line": [5, 5, 5, 5]},
        description="现代文描述",
        draft=["床前明月光", "疑是地上霜"],
        title="测试标题",
    )


def _make_pipeline(writer: _FakeWriter, checker: _FakeChecker) -> PoetryPipeline:
    """Build a pipeline with fake agents, avoiding any real LLM call.

    Args:
        writer: Fake WriterAI.
        checker: Fake CheckerAI.

    Returns:
        PoetryPipeline with the fake agents injected.

    """
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    pipeline.writer = writer
    pipeline.checker = checker
    return pipeline


def test_run_full_with_fakes() -> None:
    """Verify the full run() loop with fake agents (run/step1/step2/refine)."""
    writer = _FakeWriter(
        [
            (["窗前明月光", "疑是地上霜"], [], "炼句详情", 1),
        ]
    )
    checker = _FakeChecker([{"pass": True, "suggestions": ""}])
    pipeline = _make_pipeline(writer, checker)

    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is True
    assert state.title == "测试标题"
    assert state.final_poem == ["测试标题", "窗前明月光", "疑是地上霜"]
    assert writer.generate_description_calls == 1
    assert writer.generate_draft_calls == 1
    # The checker AI must receive the user's original prompt to verify it.
    assert checker.calls
    assert checker.calls[0]["user_prompt"] == "静夜思"
    assert checker.calls[0]["user_feedback"] == ""


def test_continue_with_feedback_passes_user_message_to_checker() -> None:
    """Verify continue feedback passes user feedback and prompt to checker."""
    writer = _FakeWriter([(["床前明月光", "疑是地上霜"], [], "炼句详情", 1)])
    checker = _FakeChecker([{"pass": True, "suggestions": ""}])
    pipeline = _make_pipeline(writer, checker)

    state = pipeline.continue_with_feedback(_make_state(), "请更婉约")

    assert state.checker_pass is True
    assert checker.calls
    assert checker.calls[0]["user_prompt"] == "静夜思"
    assert checker.calls[0]["user_feedback"] == "请更婉约"


def test_refine_checker_exception() -> None:
    """Verify a CheckerAI.check exception hits the fallback and continues."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "炼句详情", 1),
            (["窗前明月光", "疑是地上霜"], [], "炼句详情二", 1),
        ]
    )
    checker = _FakeChecker([RuntimeError("boom"), {"pass": True, "suggestions": "ok"}])
    pipeline = _make_pipeline(writer, checker)
    state = _make_state()

    events: list[dict[str, Any]] = []
    pipeline._on_progress = lambda e: events.append(e)
    messages2: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages2)

    assert state.checker_pass is True
    assert state.final_poem == ["测试标题", "窗前明月光", "疑是地上霜"]
    assert any("Checker AI error: boom" in ev["checker_suggestions"] for ev in events)


def test_refine_checker_false_then_true() -> None:
    """Verify False then True assigns continue feedback and finalizes."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "炼句详情一", 1),
            (["窗前明月光", "疑是地上霜"], [], "炼句详情二", 1),
        ]
    )
    checker = _FakeChecker(
        [
            {"pass": False, "suggestions": "请更婉约"},
            {"pass": True, "suggestions": "ok"},
        ]
    )
    pipeline = _make_pipeline(writer, checker)
    state = _make_state()

    messages3: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages3)

    assert state.checker_pass is True
    assert state.final_poem == ["测试标题", "窗前明月光", "疑是地上霜"]
    assert writer.feedback_log[1] == "请更婉约"


def test_json_dumps_safe_fallback() -> None:
    """Verify an unserializable object falls back to str."""
    bad = {1, 2, 3}
    assert json_dumps_safe(bad) == str(bad)
    assert json_dumps_safe("ok") == '"ok"'


def test_refine_zero_rounds_fallback() -> None:
    """Verify tool_rounds=0 triggers the no-refinement branch."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "炼句日志末尾", 0),
        ]
    )
    checker = _FakeChecker([{"pass": True}])
    pipeline = _make_pipeline(writer, checker)
    state = _make_state()

    messages: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages)

    assert state.checker_pass is False
    assert state.checker_suggestions == "No refinement rounds were executed"
    assert state.final_poem == ["测试标题", "床前明月光", "疑是地上霜"]


def test_run_zero_rounds_triggers_format_fallback() -> None:
    """Verify tool_rounds=0 in run() hits the format_poem fallback (391-402)."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "炼句日志末尾", 0),
        ]
    )
    checker = _FakeChecker([])
    pipeline = _make_pipeline(writer, checker)

    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is False
    assert state.final_poem == ["测试标题", "床前明月光", "疑是地上霜"]
    assert state.formatted_poem != ""
    assert "床前明月光" in state.formatted_poem


def test_fallback_formatted_poem_with_template_obj() -> None:
    """Verify the fallback when checker_pass=False and a template exists."""
    writer = _FakeWriter(
        [
            (
                ["窗前明月光", "疑是地上霜"],
                [],
                "日志",
                1,
            ),
            (
                ["窗前明月光", "疑是地上霜"],
                [],
                "日志二",
                1,
            ),
        ]
    )
    checker = _FakeChecker(
        [
            {"pass": False, "suggestions": "不够婉约"},
            {"pass": True, "suggestions": "ok"},
        ]
    )
    pipeline = _make_pipeline(writer, checker)

    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is True
    assert state.formatted_poem != ""
    assert "窗前明月光" in state.formatted_poem


# --------------------------------------------------------------------------- #
# P2-6: _load_template invalid key
# --------------------------------------------------------------------------- #
def test_load_template_invalid_key() -> None:
    """An invalid template key should raise KeyError."""
    with pytest.raises(KeyError):
        get_template("nonexistent_key_xyz")


# --------------------------------------------------------------------------- #
# P2-7: checker_pass=True + _template_obj=None -> else branch
# --------------------------------------------------------------------------- #
def test_checker_pass_no_template_obj_uses_newline_join() -> None:
    """Verify checker_pass=True with no template joins lines with newlines."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "日志", 1),
        ]
    )
    checker = _FakeChecker([{"pass": True}])
    pipeline = _make_pipeline(writer, checker)
    pipeline._template_obj = None

    state = _make_state()
    messages: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages)

    assert state.checker_pass is True
    assert state.formatted_poem == "测试标题\n床前明月光\n疑是地上霜"


# --------------------------------------------------------------------------- #
# P2-8: empty state.title keeps the title out of final_poem
# --------------------------------------------------------------------------- #
def test_empty_title_excluded_from_final_poem() -> None:
    """Verify an empty state.title leaves no title line in final_poem."""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], [], "日志", 1),
        ]
    )
    checker = _FakeChecker([{"pass": True}])
    pipeline = _make_pipeline(writer, checker)

    state = PipelineState(
        topic="静夜思",
        template_key="zh_wujue",
        template={"lines": 4, "language": "zh", "syllables_per_line": [5, 5, 5, 5]},
        description="现代文描述",
        draft=["床前明月光", "疑是地上霜"],
        title="",
    )
    messages: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages)

    assert state.title == ""
    assert state.final_poem == ["床前明月光", "疑是地上霜"]


def test_format_current_empty_title_with_template() -> None:
    """Verify formatting drops the empty first title line when no title."""
    from src.templates.zh import WujueTemplate

    pipeline = _make_pipeline(_FakeWriter([]), _FakeChecker([]))
    pipeline._template_obj = WujueTemplate()
    state = PipelineState(
        template={"lines": 2, "language": "zh"},
        draft=["白日依山尽", "黄河入海流"],
        title="",
    )
    text = pipeline._format_current(state)
    assert text.startswith("白日依山尽")
    assert "。" in text


def test_format_current_empty_draft_returns_empty() -> None:
    """Verify formatting an empty draft returns an empty string."""
    pipeline = _make_pipeline(_FakeWriter([]), _FakeChecker([]))
    state = PipelineState(template={"language": "zh"}, draft=[], title="题")
    assert pipeline._format_current(state) == ""


# --------------------------------------------------------------------------- #
# P2-9: json_dumps_safe ValueError / RecursionError branches
# --------------------------------------------------------------------------- #
def test_json_dumps_safe_value_error() -> None:
    """Verify a circular reference triggers the ValueError branch."""
    a: Any = [1]
    a.append(a)
    result = json_dumps_safe(a)
    assert isinstance(result, str)
    assert "1" in result


def test_json_dumps_safe_recursion_error() -> None:
    """Verify very deep nesting triggers the RecursionError branch."""
    deep: Any = "x"
    for _ in range(2000):
        deep = [deep]
    result = json_dumps_safe(deep)
    assert isinstance(result, str)
