# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""单元测试：补齐 pipeline.py 的缺失行覆盖（333-336/350-352/366/369/412-413/426-450）。

通过轻量假的 Writer/Checker 代理（子类化真实代理但绕过 LLMClient，绝不访问网络）
触发各类错误与边界分支：

- ``refine`` 返回 ``submitted=False``：触发 333-336 的防御分支、369 的 final_poem 兜底，
  以及 ``_describe_unsubmitted`` 的诊断逻辑（426-450）。
- ``CheckerAI.check`` 抛出异常：触发 350-352 的 except 兜底。
- ``CheckerAI.check`` 先返回 ``pass=False`` 再返回 ``pass=True``：触发 366 的续跑反馈赋值。
- 直接单测 ``json_dumps_safe`` 的序列化异常分支（412-413）与 ``_describe_unsubmitted`` 全分支。
"""

from typing import Any

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
    _describe_unsubmitted,
    json_dumps_safe,
)

RefinePlan = list[RefineResult]
CheckPlan = list[dict[str, Any] | Exception]


class _FakeWriter(WriterAI):
    """假 WriterAI：按预置 refine 结果返回，绝不构造/调用 LLMClient。"""

    def __init__(self, refine_plan: RefinePlan) -> None:
        """记录预置的 refine 返回序列，不初始化任何真实 LLM 客户端。

        Args:
            refine_plan: 依次返回的 RefineResult 列表；耗尽后再调用会抛 IndexError。
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
    ) -> tuple[str, str]:
        """返回固定描述（Step 1）。

        Args:
            topic: 主题（未使用）。
            messages: 共享消息列表（未使用）。
            on_stream: 流式回调（未使用）。

        Returns:
            (描述文本, 日志文本)。
        """
        self.generate_description_calls += 1
        return "现代文描述", "现代文描述"

    def generate_draft(
        self,
        description: str,
        template: dict[str, Any],
        messages: list[dict[str, Any]],
        template_obj: Any = None,
        max_attempts: int = 0,
        on_stream: ChunkCallback = None,
    ) -> tuple[list[str], str, str]:
        """返回固定初稿（Step 2）。

        Args:
            description: 主题描述（未使用）。
            template: 模板字典（未使用）。
            messages: 共享消息列表（未使用）。
            template_obj: 模板对象（未使用）。
            max_attempts: 已废弃参数（接口兼容，未使用）。
            on_stream: 流式回调（未使用）。

        Returns:
            (诗稿, 标题, 日志文本)。
        """
        self.generate_draft_calls += 1
        return ["床前明月光", "疑是地上霜"], "测试标题", "初稿详情"

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
    ) -> RefineResult:
        """按预置序列返回一次炼句结果，并触发 on_step 回调。

        Args:
            description: 主题描述（未使用）。
            poem: 当前诗稿（未使用）。
            template: 模板字典（未使用）。
            messages: 共享消息列表（未使用）。
            template_obj: 模板对象（未使用）。
            feedback: 检查 AI/用户反馈（未使用）。
            on_step: 每步回调。
            on_stream: 流式回调（未使用）。
            start_round: 起始轮号（未使用）。

        Returns:
            预置的 RefineResult。
        """
        self.feedback_log.append(feedback)
        result = self._refine_plan.pop(0)
        poem_out, _submitted, _history, detail, _rounds = result
        if on_step is not None:
            on_step(
                {
                    "poem": poem_out,
                    "last_tool": "submit",
                    "last_result": {},
                    "detail": detail,
                    "stream_text": "",
                }
            )
        return result


class _FakeChecker(CheckerAI):
    """假 CheckerAI：按预置结果/异常返回，绝不构造/调用 LLMClient。"""

    def __init__(self, check_results: CheckPlan) -> None:
        """记录预置的 check 返回序列（可为异常）。

        Args:
            check_results: 依次返回的结果；异常元素会被原样抛出。
        """
        self._check_results: CheckPlan = list(check_results)

    def check(
        self, description: str, poem: list[str], template: dict[str, Any]
    ) -> dict[str, Any]:
        """按预置序列返回一次终审结果；若是异常则抛出。

        Args:
            description: 主题描述（未使用）。
            poem: 诗行列表（未使用）。
            template: 模板字典（未使用）。

        Returns:
            预置的终审结果字典。

        Raises:
            预置的任意异常（用于覆盖 except 兜底分支）。
        """
        item = self._check_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_state() -> PipelineState:
    """构造一个已加载模板、可直接进入炼句循环的最小状态。

    Returns:
        PipelineState（仅含炼句循环所需字段）。
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
    """构造流水线并注入假代理，避免任何真实 LLM 调用。

    Args:
        writer: 假 WriterAI。
        checker: 假 CheckerAI。

    Returns:
        已注入假代理的 PoetryPipeline。
    """
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    pipeline.writer = writer
    pipeline.checker = checker
    return pipeline


def test_run_full_with_fakes() -> None:
    """验证注入假代理后完整 run() 闭环（覆盖 run/step1/step2/refine 主路径）。"""
    writer = _FakeWriter(
        [
            (["窗前明月光", "疑是地上霜"], True, [], "炼句详情", 1),
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


def test_refine_unsubmitted_fallback() -> None:
    """refine 返回 submitted=False 时触发 333-336 防御分支与 369 兜底。"""
    writer = _FakeWriter(
        [
            (
                ["床前明月光", "疑是地上霜"],
                False,
                [{"tool": "submit", "arguments": {}, "result": "rejected_no_changes"}],
                "炼句日志末尾",
                1,
            ),
        ]
    )
    checker = _FakeChecker([{"pass": True}])
    pipeline = _make_pipeline(writer, checker)
    state = _make_state()

    messages: list[dict[str, Any]] = []
    pipeline._run_refine_loop(state, messages)

    assert state.checker_pass is False
    assert "炼句未完成提交" in state.checker_suggestions
    assert state.final_poem == ["测试标题", "床前明月光", "疑是地上霜"]


def test_refine_checker_exception() -> None:
    """CheckerAI.check 抛出异常时触发 350-352 的 except 兜底并续跑成功。"""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], True, [], "炼句详情", 1),
            (["窗前明月光", "疑是地上霜"], True, [], "炼句详情二", 1),
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
    assert any("检查AI异常: boom" in ev["checker_suggestions"] for ev in events)


def test_refine_checker_false_then_true() -> None:
    """CheckerAI 先 False 后 True 触发 366 的续跑反馈赋值并成功定稿。"""
    writer = _FakeWriter(
        [
            (["床前明月光", "疑是地上霜"], True, [], "炼句详情一", 1),
            (["窗前明月光", "疑是地上霜"], True, [], "炼句详情二", 1),
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
    """不可序列化对象触发 412-413 的 str 兜底分支。"""
    bad = {1, 2, 3}
    assert json_dumps_safe(bad) == str(bad)
    assert json_dumps_safe("ok") == '"ok"'


def test_describe_unsubmitted_empty_history() -> None:
    """空历史触发 438 的"未调用任何工具"分支（无尾部日志）。"""
    msg = _describe_unsubmitted([], "")
    assert "AI未调用任何工具" in msg
    assert "最近日志" not in msg


def test_describe_unsubmitted_all_branches() -> None:
    """混合历史触发全部统计与尾部日志分支。"""
    history = [
        {"tool": "search_words", "result": {"words": []}},
        {"tool": "refine_line", "result": {"error": "格律未通过"}},
        {"tool": "submit", "arguments": {}, "result": "rejected_no_changes"},
        {"tool": "", "result": {}},
    ]
    detail = "\n".join(f"log{i}" for i in range(1, 9))
    msg = _describe_unsubmitted(history, detail)

    assert "submit被拒1次" in msg
    assert "工具调用失败1次" in msg
    assert "search_words" in msg
    assert "refine_line" in msg
    assert "最近日志" in msg
    assert "log8" in msg


def test_fallback_formatted_poem_with_template_obj() -> None:
    """checker_pass=False 且 _template_obj 有 format_poem 时走 411 分支。"""
    writer = _FakeWriter(
        [
            (
                ["窗前明月光", "疑是地上霜"],
                False,
                [{"tool": "submit", "arguments": {}, "result": "rejected_no_changes"}],
                "日志",
                1,
            ),
        ]
    )
    checker = _FakeChecker([{"pass": True}])
    pipeline = _make_pipeline(writer, checker)

    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is False
    assert state.formatted_poem != ""
    assert "窗前明月光" in state.formatted_poem
