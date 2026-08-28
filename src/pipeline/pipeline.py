# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""四步生成流水线与打回循环。

Step 1 描述生成 → Step 2 初稿（仅验音节）→ Step 3 炼句循环
（ReAct 工具，改完自动全量格律校验）→ Step 4 检查 AI 句意终审。
终审不通过自动打回 Step 3 继续炼句（无轮数上限，持续打回直到终审通过）；
用户"不定稿"反馈走 continue_with_feedback 续跑。
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..agents.checker_ai import CheckerAI
from ..agents.writer_ai import WriterAI
from ..config import get_config
from ..prosody.meter_validator import MeterValidator
from ..templates import get as get_template

ProgressCallback = Callable[[dict[str, Any]], None] | None


@dataclass
class PipelineState:
    """一次生成会话的完整状态（可序列化、可续跑）。"""

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
    current_step: str = ""
    final_poem: list[str] = field(default_factory=list)
    step_details: list[dict[str, Any]] = field(default_factory=list)
    last_tool: str = ""
    last_tool_result: str = ""
    stream_text: str = ""
    current_detail_step: str = ""
    current_detail: str = ""


class PoetryPipeline:
    """生成流水线：编排编写 AI、检查 AI 与符号层校验。"""

    def __init__(
        self,
        writer_config: dict[str, Any] | None = None,
        checker_config: dict[str, Any] | None = None,
    ):
        """初始化流水线。

        Args:
            writer_config: 编写 AI 配置（缺省读全局配置）。
            checker_config: 检查 AI 配置（缺省读全局配置）。
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
        """追加一条步骤详情（自动编号 seq 供前端去重）。

        Args:
            state: 流水线状态。
            **kwargs: 步骤详情字段（step/title/content/rounds 等）。
        """
        kwargs["seq"] = self._detail_seq
        self._detail_seq += 1
        state.step_details.append(kwargs)

    def _init_agents(self) -> None:
        """惰性初始化编写/检查 AI 代理。"""
        if self.writer is None:
            self.writer = WriterAI(self.writer_config)
        if self.checker is None:
            self.checker = CheckerAI(self.checker_config)

    def _get_writer(self) -> WriterAI:
        """获取编写 AI（确保已初始化）。

        Returns:
            WriterAI 实例。
        """
        self._init_agents()
        assert self.writer is not None
        return self.writer

    def _get_checker(self) -> CheckerAI:
        """获取检查 AI（确保已初始化）。

        Returns:
            CheckerAI 实例。
        """
        self._init_agents()
        assert self.checker is not None
        return self.checker

    def _load_template(self, key: str) -> dict[str, Any]:
        """加载模板对象与字典。

        Args:
            key: 模板键。

        Returns:
            模板字典（to_dict()）。
        """
        self._template_obj = get_template(key)
        return self._template_obj.to_dict()

    def _report(self, state: PipelineState) -> None:
        """推送进度事件到前端。

        Args:
            state: 流水线状态。
        """
        if self._on_progress:
            self._on_progress(
                {
                    "step": state.current_step,
                    "description": state.description,
                    "draft": state.draft,
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
        """执行完整流程（或带反馈续跑）。

        Args:
            topic: 主题。
            template_key: 模板键。
            user_feedback: 用户反馈（续跑时提供）。
            existing_state: 已有状态（续跑时提供）。
            on_progress: 进度回调。

        Returns:
            最终流水线状态。
        """
        self._on_progress = on_progress
        self._init_agents()

        if existing_state and user_feedback:
            state = existing_state
            state.user_feedback = user_feedback
            self._detail_seq = len(state.step_details)
            self._load_template(state.template_key)
            self._run_refine_loop(state)
            return state

        template_dict = self._load_template(template_key)
        state = PipelineState(
            topic=topic, template_key=template_key, template=template_dict
        )
        self._detail_seq = 0
        self._run_step1(state)
        self._run_step2(state)
        self._run_refine_loop(state)
        return state

    def _run_step1(self, state: PipelineState) -> None:
        """Step 1：生成现代文描述（流式推送）。"""
        state.current_step = "step1_description"
        state.stream_text = ""
        state.current_detail_step = "step1_description"
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str) -> None:
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        description, detail = self._get_writer().generate_description(
            state.topic, on_stream=on_stream
        )
        state.description = description
        state.stream_text = ""
        state.current_detail = ""
        self._append_detail(
            state,
            step="step1_description",
            title="Step 1: 生成现代文描述",
            content=detail,
        )
        self._report(state)

    def _run_step2(self, state: PipelineState) -> None:
        """Step 2：生成初稿（仅校验行数/音节数）。"""
        state.current_step = "step2_draft"
        state.stream_text = ""
        state.current_detail_step = "step2_draft"
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str) -> None:
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        draft, detail = self._get_writer().generate_draft(
            state.description, state.template, self._template_obj, on_stream=on_stream
        )
        state.draft = draft
        state.stream_text = ""
        self._append_detail(
            state,
            step="step2_draft",
            title="Step 2: 生成初稿",
            content=detail,
        )
        self._report(state)

    def _run_refine_loop(self, state: PipelineState) -> None:
        """Step 3→4 打回循环：炼句直到终审通过（无轮数上限）。

        炼句本身（writer.refine）无轮数上限，本外层循环在检查 AI 不通过时
        持续打回重炼，同样不设上限。
        """
        checker_feedback = state.user_feedback

        while True:
            state.current_step = "step3_refine"
            self._report(state)

            def on_step(step_info: dict[str, Any]) -> None:
                state.draft = list(step_info["poem"])
                state.last_tool = str(step_info["last_tool"])
                state.last_tool_result = json_dumps_safe(
                    step_info.get("last_result", "")
                )
                state.current_detail_step = "step3_refine"
                state.current_detail = str(step_info.get("detail", ""))
                state.stream_text = str(step_info.get("stream_text", state.stream_text))
                self._report(state)

            last_report_time: list[float] = [0.0]

            def on_stream(text: str, _t: list[float] = last_report_time) -> None:
                # _t 以默认参数绑定当前迭代的节流容器，避免闭包误捕循环变量
                now = time.monotonic()
                if now - _t[0] >= 0.25 or not text:
                    _t[0] = now
                    state.stream_text = text
                    state.last_tool = "_thinking"
                    state.last_tool_result = text
                    self._report(state)

            poem, submitted, history, detail, tool_rounds = self._get_writer().refine(
                description=state.description,
                poem=state.draft,
                template=state.template,
                template_obj=self._template_obj,
                feedback=checker_feedback,
                on_step=on_step,
                on_stream=on_stream,
                start_round=state.refine_rounds,
            )

            state.draft = poem
            state.refine_history = history
            state.refine_rounds += tool_rounds
            self._append_detail(
                state,
                step="step3_refine",
                title="Step 3: 炼句优化",
                content=detail,
                rounds=state.refine_rounds,
            )
            state.current_detail = ""

            # 防御分支: 无轮数上限后 refine() 仅在提交成功时返回，此处理论不可达
            if not submitted:
                state.checker_pass = False
                state.checker_suggestions = _describe_unsubmitted(history, detail)
                self._report(state)
                break

            state.current_step = "step4_check"
            state.stream_text = ""
            self._report(state)

            try:
                result = self._get_checker().check(
                    description=state.description,
                    poem=state.draft,
                    template=state.template,
                )
                state.checker_pass = bool(result["pass"])
                state.checker_suggestions = str(result.get("suggestions", ""))
            except Exception as e:  # noqa: BLE001 - 检查 AI 兜底：任何失败转为"未通过+建议"
                state.checker_pass = False
                state.checker_suggestions = f"检查AI异常: {e}"

            self._append_detail(
                state,
                step="step4_check",
                title="Step 4: 检查AI终审",
                content=f"pass={state.checker_pass}\n{state.checker_suggestions}",
            )
            self._report(state)

            if state.checker_pass:
                state.final_poem = state.draft
                break

            checker_feedback = state.checker_suggestions

        if not state.checker_pass and not state.final_poem:
            state.final_poem = state.draft

    def continue_with_feedback(
        self,
        state: PipelineState,
        user_feedback: str,
        on_progress: ProgressCallback = None,
    ) -> PipelineState:
        """按用户反馈续跑（打回 Step 3 重新炼句）。

        Args:
            state: 已有状态。
            user_feedback: 用户反馈文本。
            on_progress: 进度回调。

        Returns:
            续跑后的状态。
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
    """安全 JSON 序列化（失败时降级为 str）。

    json.dumps 的失败类型为 TypeError（不可序列化）、ValueError（循环引用）、
    RecursionError（过深嵌套）。

    Args:
        obj: 任意对象。
        default: 序列化失败时的兜底。

    Returns:
        JSON 字符串。
    """
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        return str(obj)


def _describe_unsubmitted(history: list[dict[str, Any]], detail: str) -> str:
    """生成"炼句未完成提交"的诊断说明。

    Args:
        history: 炼句工具历史。
        detail: 炼句日志。

    Returns:
        诊断文本（含统计与最近日志）。
    """
    rejected = 0
    failed = 0
    for h in history:
        result = h.get("result")
        if h.get("tool") == "submit" and result == "rejected_no_changes":
            rejected += 1
        if isinstance(result, dict) and result.get("error"):
            failed += 1
    tool_calls = [
        str(h.get("tool")) for h in history if h.get("tool") not in ("submit", "")
    ]
    stats: list[str] = []
    if not tool_calls:
        stats.append("AI未调用任何工具(可能模型不支持工具调用)")
    else:
        if rejected:
            stats.append(f"submit被拒{rejected}次(须先成功修改一行)")
        if failed:
            stats.append(f"工具调用失败{failed}次(多为格律未通过)")
        stats.append(f"已执行工具: {'、'.join(dict.fromkeys(tool_calls))}")
    tail_lines = detail.strip().splitlines()[-6:] if detail else []
    msg = "炼句未完成提交: " + "；".join(stats)
    if tail_lines:
        msg += "\n最近日志:\n" + "\n".join(tail_lines)
    return msg
