# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..agents.writer_ai import WriterAI
from ..agents.checker_ai import CheckerAI
from ..prosody.meter_validator import MeterValidator
from ..config import get_config
from ..templates import get as get_template


@dataclass
class PipelineState:
    topic: str = ""
    template_key: str = ""
    template: dict = field(default_factory=dict)
    description: str = ""
    draft: list[str] = field(default_factory=list)
    refine_rounds: int = 0
    refine_history: list[dict] = field(default_factory=list)
    checker_pass: bool = False
    checker_suggestions: str = ""
    user_feedback: str = ""
    current_step: str = ""
    final_poem: list[str] = field(default_factory=list)
    step_details: list[dict] = field(default_factory=list)
    last_tool: str = ""
    last_tool_result: str = ""
    stream_text: str = ""
    current_detail_step: str = ""
    current_detail: str = ""


class PoetryPipeline:
    def __init__(
        self, writer_config: dict | None = None, checker_config: dict | None = None
    ):
        config = get_config()
        self.writer_config = writer_config or config.writer
        self.checker_config = checker_config or config.checker
        self.writer: Optional[WriterAI] = None
        self.checker: Optional[CheckerAI] = None
        self.validator = MeterValidator()
        self._on_progress: Optional[Callable] = None
        self._template_obj = None

    def _init_agents(self):
        if self.writer is None:
            self.writer = WriterAI(self.writer_config)
        if self.checker is None:
            self.checker = CheckerAI(self.checker_config)

    def _load_template(self, key: str):
        self._template_obj = get_template(key)
        return self._template_obj.to_dict()

    def _report(self, state: PipelineState):
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
        existing_state: Optional[PipelineState] = None,
        on_progress: Optional[Callable] = None,
    ) -> PipelineState:
        self._on_progress = on_progress
        self._init_agents()

        if existing_state and user_feedback:
            state = existing_state
            state.user_feedback = user_feedback
            self._load_template(state.template_key)
            self._run_refine_loop(state)
            return state

        template_dict = self._load_template(template_key)
        state = PipelineState(
            topic=topic, template_key=template_key, template=template_dict
        )
        self._run_step1(state)
        self._run_step2(state)
        self._run_refine_loop(state)
        return state

    def _run_step1(self, state: PipelineState):
        state.current_step = "step1_description"
        state.stream_text = ""
        state.current_detail_step = "step1_description"
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str):
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        description, detail = self.writer.generate_description(
            state.topic, on_stream=on_stream
        )
        state.description = description
        state.stream_text = ""
        state.current_detail = ""
        state.step_details.append(
            {
                "step": "step1_description",
                "title": "Step 1: 生成现代文描述",
                "content": detail,
            }
        )
        self._report(state)

    def _run_step2(self, state: PipelineState):
        state.current_step = "step2_draft"
        state.stream_text = ""
        state.current_detail_step = "step2_draft"
        state.current_detail = ""
        self._report(state)

        last_report_time = [0.0]

        def on_stream(text: str):
            now = time.monotonic()
            if now - last_report_time[0] >= 0.25 or not text:
                last_report_time[0] = now
                state.stream_text = text
                state.current_detail = text
                self._report(state)

        draft, detail = self.writer.generate_draft(
            state.description, state.template, self._template_obj, on_stream=on_stream
        )
        state.draft = draft
        state.stream_text = ""
        state.step_details.append(
            {
                "step": "step2_draft",
                "title": "Step 2: 生成初稿",
                "content": detail,
            }
        )
        self._report(state)

    def _run_refine_loop(self, state: PipelineState):
        max_outer_loops = 10
        checker_feedback = state.user_feedback

        for outer in range(max_outer_loops):
            state.current_step = "step3_refine"
            self._report(state)

            def on_step(step_info: dict):
                state.draft = step_info["poem"]
                state.last_tool = step_info["last_tool"]
                state.last_tool_result = json_dumps_safe(
                    step_info.get("last_result", "")
                )
                state.current_detail_step = "step3_refine"
                state.current_detail = step_info.get("detail", "")
                state.stream_text = step_info.get("stream_text", state.stream_text)
                self._report(state)

            last_report_time = [0.0]

            def on_stream(text: str):
                now = time.monotonic()
                if now - last_report_time[0] >= 0.25 or not text:
                    last_report_time[0] = now
                    state.stream_text = text
                    state.last_tool = "_thinking"
                    state.last_tool_result = text
                    self._report(state)

            poem, submitted, history, detail, tool_rounds = self.writer.refine(
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
            state.step_details.append(
                {
                    "step": "step3_refine",
                    "title": "Step 3: 炼句优化",
                    "content": detail,
                    "rounds": state.refine_rounds,
                }
            )

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
                result = self.checker.check(
                    description=state.description,
                    poem=state.draft,
                    template=state.template,
                )
                state.checker_pass = result["pass"]
                state.checker_suggestions = result.get("suggestions", "")
            except Exception as e:
                state.checker_pass = False
                state.checker_suggestions = f"检查AI异常: {e}"

            state.step_details.append(
                {
                    "step": "step4_check",
                    "title": "Step 4: 检查AI终审",
                    "content": f"pass={state.checker_pass}\n{state.checker_suggestions}",
                }
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
        on_progress: Optional[Callable] = None,
    ) -> PipelineState:
        self._on_progress = on_progress
        return self.run(
            topic=state.topic,
            template_key=state.template_key,
            user_feedback=user_feedback,
            existing_state=state,
            on_progress=on_progress,
        )


def json_dumps_safe(obj, default=""):
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _describe_unsubmitted(history: list[dict], detail: str) -> str:
    """生成'炼句未完成提交'的诊断说明，让用户看到卡在哪个环节。"""
    rejected = sum(
        1
        for h in history
        if h.get("tool") == "submit" and h.get("result") == "rejected_no_changes"
    )
    failed = sum(
        1
        for h in history
        if isinstance(h.get("result"), dict) and h.get("result").get("error")
    )
    tool_calls = [h.get("tool") for h in history if h.get("tool") not in ("submit", "")]
    stats = []
    if not tool_calls:
        stats.append("AI未调用任何工具(可能模型不支持工具调用)")
    else:
        if rejected:
            stats.append(f"submit被拒{rejected}次(须先成功修改一行)")
        if failed:
            stats.append(f"工具调用失败{failed}次(多为格律未通过)")
        stats.append(f"已执行工具: {'、'.join(dict.fromkeys(tool_calls))}")
    tail_lines = detail.strip().splitlines()[-6:] if detail else []
    msg = "炼句未完成提交(20轮内未成功提交): " + "；".join(stats)
    if tail_lines:
        msg += "\n最近日志:\n" + "\n".join(tail_lines)
    return msg
