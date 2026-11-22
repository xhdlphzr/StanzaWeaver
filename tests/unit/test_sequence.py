# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for poem-sequence planning / architect / pipeline (offline, stubbed LLM)."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.agents.architect_ai import PlanResult, SequenceArchitect
from src.pipeline.pipeline import PipelineState
from src.pipeline.sequence import PoemSequencePipeline, SequencePoemState, SequenceState
from src.tools.planning import (
    PlanState,
    SequencePoemPlan,
    execute_add_poem,
    execute_set_poem_prompt,
    execute_set_sequence_title,
    missing_prompt_indices,
    render_plan,
)

CATALOG: list[dict[str, Any]] = [
    {
        "key": "zh_wujue",
        "name": "五言绝句",
        "display_name": "五言绝句（汉语）",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
    },
    {
        "key": "zh_rumengling",
        "name": "如梦令",
        "display_name": "如梦令（汉语）",
        "lines": 7,
        "syllables_per_line": [6, 6, 5, 6, 2, 2, 6],
    },
]
VALID = {"zh_wujue", "zh_rumengling"}


def _tool(name: str, cid: str, **arguments: Any) -> dict[str, Any]:
    """Build one tool-call response.

    Args:
        name: Tool name.
        cid: Call id.
        **arguments: Tool arguments.

    Returns:
        A dict shaped like ChatResult.

    """
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": cid, "name": name, "arguments": arguments}],
    }


def _no_tools() -> dict[str, Any]:
    """Build a response with no tool calls.

    Returns:
        A dict shaped like ChatResult.

    """
    return {"role": "assistant", "content": "", "tool_calls": []}


def _make_architect(responses: list[dict[str, Any]]) -> SequenceArchitect:
    """Build an architect with preset responses.

    Args:
        responses: Responses returned by chat in order.

    Returns:
        A SequenceArchitect instance (client already replaced by MagicMock).

    """
    with patch("src.agents.architect_ai.LLMClient"):
        architect = SequenceArchitect({"base_url": "x", "api_key": "x", "model": "x"})
    architect.client = MagicMock()
    architect.client.chat.side_effect = list(responses)
    return architect


# --------------------------------------------------------------------------- #
# Planning tools
# --------------------------------------------------------------------------- #
def test_planning_tools_state_and_render() -> None:
    """Planning tools: title / add poem / set brief / missing detection / render."""
    state = PlanState()
    assert "error" in execute_set_sequence_title(state, {"title": " "})
    assert execute_set_sequence_title(state, {"title": "四季"})["status"] == "ok"

    assert "error" in execute_add_poem(
        state, {"title": "", "template_key": "zh_wujue"}, VALID
    )
    assert "error" in execute_add_poem(
        state, {"title": "春", "template_key": "nope"}, VALID
    )
    assert (
        execute_add_poem(state, {"title": "春", "template_key": "zh_wujue"}, VALID)[
            "index"
        ]
        == 0
    )
    assert (
        execute_add_poem(
            state, {"title": "夏", "template_key": "zh_rumengling"}, VALID
        )["index"]
        == 1
    )

    assert missing_prompt_indices(state) == [0, 1]
    assert "error" in execute_set_poem_prompt(state, {"index": "x", "prompt": "p"})
    assert "error" in execute_set_poem_prompt(state, {"index": 9, "prompt": "p"})
    assert "error" in execute_set_poem_prompt(state, {"index": 0, "prompt": " "})
    assert (
        execute_set_poem_prompt(state, {"index": 0, "prompt": "写春"})["status"] == "ok"
    )
    assert missing_prompt_indices(state) == [1]

    text = render_plan(state, {"zh_wujue": "五言绝句"})
    assert "四季" in text
    assert '"春" [五言绝句]' in text
    assert "写春" in text
    assert "(no creative requirements set)" in text


def test_render_plan_empty_title() -> None:
    """render_plan falls back to "Untitled" when there is no title."""
    assert '"Untitled"' in render_plan(PlanState())


# --------------------------------------------------------------------------- #
# Architect planning loop
# --------------------------------------------------------------------------- #
def test_architect_plan_completes() -> None:
    """Architect: tools fill title/poems/briefs in one round; stopping completes."""
    architect = _make_architect(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "set_sequence_title",
                        "arguments": {"title": "四季"},
                    },
                    {
                        "id": "2",
                        "name": "add_poem",
                        "arguments": {"title": "春", "template_key": "zh_wujue"},
                    },
                    {
                        "id": "3",
                        "name": "set_poem_prompt",
                        "arguments": {"index": 0, "prompt": "写春"},
                    },
                ],
            },
            _no_tools(),
        ]
    )
    plan = architect.plan("四季组诗", catalog=CATALOG)
    assert plan.completed is True
    assert plan.title == "四季"
    assert plan.poems[0].title == "春"
    assert plan.poems[0].prompt == "写春"
    assert "set_sequence_title" in plan.log


def test_architect_plan_feedback_then_complete() -> None:
    """Architect: feeds back a reminder for missing briefs; completes after filling."""
    architect = _make_architect(
        [
            _tool("set_sequence_title", "1", title="四季"),
            _tool("add_poem", "2", title="春", template_key="zh_wujue"),
            _no_tools(),
            _tool("set_poem_prompt", "3", index=0, prompt="写春"),
            _no_tools(),
        ]
    )
    plan = architect.plan("四季组诗", catalog=CATALOG)
    assert plan.completed is True
    assert "reminder" in plan.log


def test_architect_plan_unknown_tool_and_max_rounds() -> None:
    """Unknown tools are recorded as errors; still incomplete at max rounds."""
    architect = _make_architect(
        [
            _tool("bogus", "1"),
            _tool("add_poem", "2", title="春", template_key="zh_wujue"),
        ]
    )
    plan = architect.plan("x", catalog=CATALOG, max_rounds=2)
    assert plan.completed is False
    assert "Unknown planning tool" in plan.log


def test_architect_plan_missing_title_and_poems() -> None:
    """Feed back reminders for a missing title / no poems; default catalog covered."""
    architect = _make_architect([_no_tools(), _no_tools()])
    plan = architect.plan("x", max_rounds=2)
    assert plan.completed is False
    assert "overall sequence title" in plan.log

    architect2 = _make_architect(
        [_tool("set_sequence_title", "1", title="题"), _no_tools()]
    )
    plan2 = architect2.plan("x", catalog=CATALOG, max_rounds=2)
    assert plan2.completed is False
    assert "add at least one poem" in plan2.log


# --------------------------------------------------------------------------- #
# Sequence pipeline
# --------------------------------------------------------------------------- #
class _FakeArchitect:
    """Fake architect returning a preset PlanResult."""

    def __init__(self, result: PlanResult) -> None:
        self.result = result
        self.seed: list[SequencePoemPlan] | None = None

    def plan(
        self,
        topic: str,
        catalog: list[dict[str, Any]] | None = None,
        max_rounds: int = 12,
        poems: list[SequencePoemPlan] | None = None,
    ) -> PlanResult:
        self.seed = poems
        return self.result


class _FakePoemPipeline:
    """Fake pipeline that records topics and returns a fixed single-poem result."""

    def __init__(self, checker_pass: bool = True) -> None:
        self.checker_pass = checker_pass
        self.topics: list[str] = []

    def run(
        self,
        topic: str,
        template_key: str,
        on_progress: Any = None,
    ) -> PipelineState:
        self.topics.append(topic)
        if on_progress:
            on_progress(
                {
                    "draft": ["句一", "句二"],
                    "title": "题",
                    "refine_rounds": 1,
                    "checker_pass": self.checker_pass,
                    "checker_suggestions": "",
                    "formatted_poem": "句一，句二。",
                    "language": "zh",
                }
            )
        return PipelineState(
            draft=["句一", "句二"],
            title="题",
            punctuation=["，", "。"],
            checker_pass=self.checker_pass,
            checker_suggestions="",
            formatted_poem="句一，句二。",
            refine_rounds=1,
        )


def _sequence_pipeline(
    result: PlanResult, checker_pass: bool = True
) -> tuple[Any, Any]:
    """Build a sequence pipeline with a fake architect and fake poem pipeline.

    Args:
        result: The plan result returned by the fake architect.
        checker_pass: Final-check result of the fake single-poem pipeline.

    Returns:
        (sequence pipeline, fake single-poem pipeline).

    """
    pipeline = PoemSequencePipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    pipeline.architect = cast(Any, _FakeArchitect(result))
    fake = _FakePoemPipeline(checker_pass=checker_pass)
    pipeline._make_poem_pipeline = lambda: fake  # type: ignore[method-assign, assignment, return-value]
    return pipeline, fake


def test_sequence_pipeline_composes_all_poems() -> None:
    """Sequence pipeline: compose poem by poem, inject previous works, report ok."""
    plan = PlanResult(
        True,
        "四季",
        [
            SequencePoemPlan("春", "zh_wujue", "写春"),
            SequencePoemPlan("夏", "zh_rumengling", "写夏"),
        ],
        "",
    )
    pipeline, fake = _sequence_pipeline(plan)
    events: list[dict[str, Any]] = []
    state = pipeline.run("四季组诗", on_progress=events.append)

    assert state.completed is True
    assert state.ok is True
    assert len(state.poems) == 2
    assert state.poems[0].formatted_poem == "句一，句二。"
    assert "[Sequence goal] 四季组诗" in fake.topics[0]
    assert "[This poem's requirements] 写春" in fake.topics[0]
    assert "[Previously written]" not in fake.topics[0]
    assert "[Previously written]" in fake.topics[1]
    assert 'Poem 1 "题" first line: 句一' in fake.topics[1]
    assert any("plan_text" in e for e in events)


def test_sequence_pipeline_checker_failure() -> None:
    """Sequence ok is False when any single poem fails final review."""
    plan = PlanResult(True, "题", [SequencePoemPlan("春", "zh_wujue", "写春")], "")
    pipeline, _ = _sequence_pipeline(plan, checker_pass=False)
    state = pipeline.run("x")
    assert state.completed is True
    assert state.ok is False


def test_sequence_pipeline_incomplete_plan() -> None:
    """Return incomplete directly when the plan is incomplete or has no poems."""
    pipeline, fake = _sequence_pipeline(PlanResult(False, "", [], ""))
    state = pipeline.run("x")
    assert state.completed is False
    assert state.ok is False
    assert fake.topics == []

    pipeline2, _ = _sequence_pipeline(PlanResult(True, "题", [], ""))
    state2 = pipeline2.run("x")
    assert state2.completed is False


def test_sequence_poem_instruction_previous_without_draft() -> None:
    """Use the "(unfinished)" placeholder when a previous poem has no draft."""
    pipeline, _ = _sequence_pipeline(PlanResult(True, "题", [], ""))
    state = SequenceState(
        topic="总目标",
        title="题",
        poems=[
            SequencePoemState(title="其一", template_key="zh_wujue", prompt="写一"),
            SequencePoemState(title="其二", template_key="zh_wujue", prompt="写二"),
        ],
    )
    text = pipeline._poem_instruction(state, 1)
    assert "(unfinished)" in text


def test_sequence_pipeline_lazy_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default architect and poem-pipeline factories can be built lazily."""
    import src.pipeline.sequence as sequence_module

    created: dict[str, Any] = {}

    class _Arch:
        def __init__(self, config: dict[str, Any]) -> None:
            created["arch"] = config

    class _Pipe:
        def __init__(self, writer: dict[str, Any], checker: dict[str, Any]) -> None:
            created["pipe"] = (writer, checker)

    monkeypatch.setattr(sequence_module, "SequenceArchitect", _Arch)
    monkeypatch.setattr(sequence_module, "PoetryPipeline", _Pipe)
    pipeline = PoemSequencePipeline(
        writer_config={"base_url": "w", "api_key": "k", "model": "m"},
        checker_config={"base_url": "c", "api_key": "k", "model": "m"},
    )
    architect = pipeline._get_architect()
    assert isinstance(architect, _Arch)
    assert pipeline._get_architect() is architect
    poem_pipeline = pipeline._make_poem_pipeline()
    assert isinstance(poem_pipeline, _Pipe)
    assert created["pipe"][0]["base_url"] == "w"


def test_architect_fixed_mode_only_prompts() -> None:
    """Fixed poem count/meter: hide add_poem; only title and briefs are needed."""
    architect = _make_architect(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "set_sequence_title",
                        "arguments": {"title": "四季"},
                    },
                    {
                        "id": "2",
                        "name": "set_poem_prompt",
                        "arguments": {"index": 0, "prompt": "写春"},
                    },
                    {
                        "id": "3",
                        "name": "set_poem_prompt",
                        "arguments": {"index": 1, "prompt": "写夏"},
                    },
                ],
            },
            _no_tools(),
        ]
    )
    seed = [
        SequencePoemPlan("第1首", "zh_wujue"),
        SequencePoemPlan("第2首", "zh_rumengling"),
    ]
    plan = architect.plan("四季组诗", catalog=CATALOG, poems=seed)
    assert plan.completed is True
    assert plan.title == "四季"
    assert [p.prompt for p in plan.poems] == ["写春", "写夏"]
    assert [p.template_key for p in plan.poems] == ["zh_wujue", "zh_rumengling"]

    calls = cast(Any, architect.client).chat.call_args_list
    tools = calls[0].kwargs["tools"]
    names = [tool["function"]["name"] for tool in tools]
    assert "add_poem" not in names
    assert "set_poem_prompt" in names


def test_architect_fixed_mode_rejects_add_poem() -> None:
    """In fixed mode even a model call to add_poem is rejected."""
    architect = _make_architect(
        [
            _tool("set_sequence_title", "1", title="题"),
            _tool("add_poem", "2", title="春", template_key="zh_wujue"),
        ]
    )
    plan = architect.plan(
        "x",
        catalog=CATALOG,
        poems=[SequencePoemPlan("第1首", "zh_wujue")],
        max_rounds=2,
    )
    assert plan.completed is False
    assert "poem count is fixed" in plan.log.lower()


def test_sequence_pipeline_seeds_templates() -> None:
    """The poem list is fixed up front and passed to the architect when seeded."""
    plan = PlanResult(
        True,
        "四季",
        [
            SequencePoemPlan("第1首", "zh_wujue", "写春"),
            SequencePoemPlan("第2首", "zh_rumengling", "写夏"),
        ],
        "",
    )
    pipeline, _ = _sequence_pipeline(plan)
    state = pipeline.run("四季", template_keys=["zh_wujue", "zh_rumengling"])
    assert state.ok is True
    assert [p.template_key for p in state.poems] == ["zh_wujue", "zh_rumengling"]
    assert state.poems[0].centered is True
    assert state.poems[1].centered is False
    architect = cast(Any, pipeline.architect)
    assert architect.seed is not None
    assert [p.title for p in architect.seed] == ["Poem 1", "Poem 2"]
    assert [p.template_key for p in architect.seed] == ["zh_wujue", "zh_rumengling"]


def test_sequence_pipeline_invalid_template_keys() -> None:
    """An empty or unknown meter key raises immediately."""
    pipeline, _ = _sequence_pipeline(PlanResult(True, "题", [], ""))
    with pytest.raises(ValueError):
        pipeline.run("x", template_keys=[])
    with pytest.raises(ValueError):
        pipeline.run("x", template_keys=["nope"])


def test_centered_flag_shi_vs_ci() -> None:
    """Shi are centered and ci are not; the flag drives frontend alignment via to_dict."""
    from src.templates.zh import (
        LangtaoshaTemplate,
        QingpingyueTemplate,
        RumenglingTemplate,
        WujueTemplate,
        XiangjianhuanTemplate,
    )

    assert WujueTemplate().centered is True
    assert WujueTemplate().to_dict()["centered"] is True
    for tpl in (
        XiangjianhuanTemplate(),
        RumenglingTemplate(),
        LangtaoshaTemplate(),
        QingpingyueTemplate(),
    ):
        assert tpl.centered is False
        assert tpl.to_dict()["centered"] is False
