# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""诗组规划 / 架构师 / 诗组流水线单元测试（离线，桩 LLM）."""

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
    """构造一个工具调用响应.

    Args:
        name: 工具名。
        cid: 调用 id。
        **arguments: 工具参数。

    Returns:
        ChatResult 形状的字典。

    """
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": cid, "name": name, "arguments": arguments}],
    }


def _no_tools() -> dict[str, Any]:
    """构造无工具调用的响应.

    Returns:
        ChatResult 形状的字典。

    """
    return {"role": "assistant", "content": "", "tool_calls": []}


def _make_architect(responses: list[dict[str, Any]]) -> SequenceArchitect:
    """构造带预置响应的架构师.

    Args:
        responses: chat 依次返回的响应。

    Returns:
        SequenceArchitect 实例（client 已被替换为 MagicMock）。

    """
    with patch("src.agents.architect_ai.LLMClient"):
        architect = SequenceArchitect({"base_url": "x", "api_key": "x", "model": "x"})
    architect.client = MagicMock()
    architect.client.chat.side_effect = list(responses)
    return architect


# --------------------------------------------------------------------------- #
# 规划工具
# --------------------------------------------------------------------------- #
def test_planning_tools_state_and_render() -> None:
    """规划工具：标题 / 加诗 / 设要求 / 缺失检测 / 计划渲染."""
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
    assert "《春》[五言绝句]" in text
    assert "写春" in text
    assert "（未设置创作要求）" in text


def test_render_plan_empty_title() -> None:
    """render_plan 在无标题时回退为“未命名”."""
    assert "未命名" in render_plan(PlanState())


# --------------------------------------------------------------------------- #
# 架构师规划循环
# --------------------------------------------------------------------------- #
def test_architect_plan_completes() -> None:
    """架构师：一轮工具补齐标题/诗题/要求后，停止调用即完成."""
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
    """架构师：缺要求时回灌提醒，补齐后完成."""
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
    assert "提醒" in plan.log


def test_architect_plan_unknown_tool_and_max_rounds() -> None:
    """未知工具记错误；达到最大轮数仍未完整则返回未完成."""
    architect = _make_architect(
        [
            _tool("bogus", "1"),
            _tool("add_poem", "2", title="春", template_key="zh_wujue"),
        ]
    )
    plan = architect.plan("x", catalog=CATALOG, max_rounds=2)
    assert plan.completed is False
    assert "未知规划工具" in plan.log


def test_architect_plan_missing_title_and_poems() -> None:
    """无标题 / 无诗时回灌对应提醒；默认 catalog 分支也被覆盖."""
    architect = _make_architect([_no_tools(), _no_tools()])
    plan = architect.plan("x", max_rounds=2)
    assert plan.completed is False
    assert "诗组总标题" in plan.log

    architect2 = _make_architect(
        [_tool("set_sequence_title", "1", title="题"), _no_tools()]
    )
    plan2 = architect2.plan("x", catalog=CATALOG, max_rounds=2)
    assert plan2.completed is False
    assert "至少添加一首诗" in plan2.log


# --------------------------------------------------------------------------- #
# 诗组流水线
# --------------------------------------------------------------------------- #
class _FakeArchitect:
    """返回预置 PlanResult 的假架构师."""

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
    """记录 topic 并返回固定单首结果的假流水线."""

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
    """构造注入了假架构师/假单首流水线的诗组流水线.

    Args:
        result: 架构师返回的规划结果。
        checker_pass: 假单首流水线的终审结果。

    Returns:
        (诗组流水线, 假单首流水线)。

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
    """诗组流水线：逐首生成、注入前作、汇总 ok."""
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
    assert "【诗组总目标】四季组诗" in fake.topics[0]
    assert "【本首要求】写春" in fake.topics[0]
    assert "【前面已创作】" not in fake.topics[0]
    assert "【前面已创作】" in fake.topics[1]
    assert "第1首《题》首句：句一" in fake.topics[1]
    assert any("plan_text" in e for e in events)


def test_sequence_pipeline_checker_failure() -> None:
    """任一首终审不过时诗组 ok 为 False."""
    plan = PlanResult(True, "题", [SequencePoemPlan("春", "zh_wujue", "写春")], "")
    pipeline, _ = _sequence_pipeline(plan, checker_pass=False)
    state = pipeline.run("x")
    assert state.completed is True
    assert state.ok is False


def test_sequence_pipeline_incomplete_plan() -> None:
    """规划未完成或没有诗时直接返回未完成."""
    pipeline, fake = _sequence_pipeline(PlanResult(False, "", [], ""))
    state = pipeline.run("x")
    assert state.completed is False
    assert state.ok is False
    assert fake.topics == []

    pipeline2, _ = _sequence_pipeline(PlanResult(True, "题", [], ""))
    state2 = pipeline2.run("x")
    assert state2.completed is False


def test_sequence_poem_instruction_previous_without_draft() -> None:
    """前作尚无草稿时用“（未完成）”占位."""
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
    assert "（未完成）" in text


def test_sequence_pipeline_lazy_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认架构师与单首流水线工厂可被惰性构造."""
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
    """固定诗数/格律时：不暴露 add_poem，只要求设标题与逐首提示词."""
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
    """固定模式下即使模型调用 add_poem 也会被拒绝."""
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
    assert "诗数已固定" in plan.log


def test_sequence_pipeline_seeds_templates() -> None:
    """提供 template_keys 时预先固定诗单并交给架构师."""
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
    architect = cast(Any, pipeline.architect)
    assert architect.seed is not None
    assert [p.title for p in architect.seed] == ["第1首", "第2首"]
    assert [p.template_key for p in architect.seed] == ["zh_wujue", "zh_rumengling"]


def test_sequence_pipeline_invalid_template_keys() -> None:
    """空/未知格律 key 直接报错."""
    pipeline, _ = _sequence_pipeline(PlanResult(True, "题", [], ""))
    with pytest.raises(ValueError):
        pipeline.run("x", template_keys=[])
    with pytest.raises(ValueError):
        pipeline.run("x", template_keys=["nope"])
