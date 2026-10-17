# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""诗组流水线：规划 → 逐首生成/检查 → 汇总.

Step 1 由 SequenceArchitect 规划诗组标题与每首诗的格律/创作要求；
Step 2 按顺序为每首诗开启独立会话，复用单首 PoetryPipeline（描述 → 初稿 →
炼句 → 检查 AI 终审），并把诗组总目标与前面已完成诗作注入当前诗；
全部完成后汇总为诗组结果。跨首一致性靠规划与注入，不另做整组符号检查。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..agents.architect_ai import SequenceArchitect
from ..config import get_config
from ..templates import get as get_template
from ..templates import list_dicts
from ..tools.planning import PlanState, SequencePoemPlan, render_plan
from .pipeline import PoetryPipeline

ProgressCallback = Callable[[dict[str, Any]], None] | None


@dataclass
class SequencePoemState:
    """诗组中单首诗的生成状态."""

    title: str
    template_key: str
    prompt: str
    draft: list[str] = field(default_factory=list)
    final_title: str = ""
    punctuation: list[str] = field(default_factory=list)
    checker_pass: bool = False
    checker_suggestions: str = ""
    formatted_poem: str = ""
    rounds: int = 0
    done: bool = False


@dataclass
class SequenceState:
    """一次诗组生成的完整状态."""

    topic: str = ""
    title: str = ""
    plan_text: str = ""
    plan_completed: bool = False
    poems: list[SequencePoemState] = field(default_factory=list)
    current_index: int = 0
    completed: bool = False
    ok: bool = False


class PoemSequencePipeline:
    """诗组流水线：架构师规划 → 逐首走单首流水线 → 汇总."""

    def __init__(
        self,
        writer_config: dict[str, Any] | None = None,
        checker_config: dict[str, Any] | None = None,
    ):
        """初始化诗组流水线.

        Args:
            writer_config: 编写/架构 AI 配置（缺省读全局配置）。
            checker_config: 检查 AI 配置（缺省读全局配置）。

        """
        config = get_config()
        self.writer_config = writer_config or config.writer
        self.checker_config = checker_config or config.checker
        self.architect: SequenceArchitect | None = None
        self._on_progress: ProgressCallback = None

    def _get_architect(self) -> SequenceArchitect:
        """获取架构师（惰性初始化）.

        Returns:
            SequenceArchitect 实例。

        """
        if self.architect is None:
            self.architect = SequenceArchitect(self.writer_config)
        return self.architect

    def _make_poem_pipeline(self) -> PoetryPipeline:
        """创建单首流水线（便于测试替换）.

        Returns:
            PoetryPipeline 实例。

        """
        return PoetryPipeline(self.writer_config, self.checker_config)

    def run(
        self,
        topic: str,
        on_progress: ProgressCallback = None,
        max_rounds: int = 12,
        template_keys: list[str] | None = None,
    ) -> SequenceState:
        """执行诗组生成.

        Args:
            topic: 诗组总目标。
            on_progress: 进度回调。
            max_rounds: 规划最大轮数。
            template_keys: 用户固定的每首格律 key 列表；提供时不再由架构师
                新增诗，仅让其设定诗组标题与每首创作要求。

        Returns:
            最终诗组状态。

        Raises:
            ValueError: template_keys 为空或包含未知模板。

        """
        self._on_progress = on_progress
        catalog = list_dicts()
        seed: list[SequencePoemPlan] | None = None
        if template_keys is not None:
            if not template_keys:
                raise ValueError("诗组至少需要一首诗")
            seed = []
            for index, key in enumerate(template_keys, 1):
                try:
                    get_template(key)
                except KeyError as exc:
                    raise ValueError(f"未知格律模板 key: {key}") from exc
                seed.append(SequencePoemPlan(title=f"第{index}首", template_key=key))
        plan = self._get_architect().plan(
            topic, catalog=catalog, max_rounds=max_rounds, poems=seed
        )
        names = {str(item["key"]): str(item["name"]) for item in catalog}
        state = SequenceState(
            topic=topic,
            title=plan.title,
            plan_text=render_plan(
                PlanState(title=plan.title, poems=list(plan.poems)), names
            ),
            plan_completed=plan.completed,
            poems=[
                SequencePoemState(
                    title=p.title, template_key=p.template_key, prompt=p.prompt
                )
                for p in plan.poems
            ],
        )
        if not plan.completed or not state.poems:
            self._report(state)
            return state

        for index in range(len(state.poems)):
            state.current_index = index
            self._report(state)
            poem = state.poems[index]
            instruction = self._poem_instruction(state, index)
            inner = self._make_poem_pipeline().run(
                topic=instruction,
                template_key=poem.template_key,
                on_progress=self._poem_progress_callback(state, index),
            )
            poem.draft = list(inner.draft)
            poem.final_title = inner.title
            poem.punctuation = list(inner.punctuation)
            poem.checker_pass = bool(inner.checker_pass)
            poem.checker_suggestions = str(inner.checker_suggestions)
            poem.formatted_poem = str(inner.formatted_poem)
            poem.rounds = int(inner.refine_rounds)
            poem.done = True
            self._report(state)

        state.completed = all(p.done for p in state.poems)
        state.ok = state.completed and all(p.checker_pass for p in state.poems)
        self._report(state)
        return state

    def _poem_instruction(self, state: SequenceState, index: int) -> str:
        """构造第 index 首诗的生成指令（总目标 + 本首要求 + 前作摘要）.

        Args:
            state: 诗组状态。
            index: 诗序号（0-based）。

        Returns:
            作为单首流水线 topic 的指令文本。

        """
        poem = state.poems[index]
        tpl = get_template(poem.template_key)
        parts = [
            f"【诗组总目标】{state.topic}",
            f"【诗组标题】{state.title}",
            f"【本首要求】{poem.prompt}",
            f"【本首格律】{tpl.name}（{tpl.language}，{tpl.lines} 行）\n{tpl.describe()}",
        ]
        previous = state.poems[:index]
        if previous:
            lines: list[str] = []
            for number, prev in enumerate(previous, 1):
                first_line = prev.draft[0] if prev.draft else "（未完成）"
                title = prev.final_title or prev.title
                lines.append(f"第{number}首《{title}》首句：{first_line}")
            parts.append("【前面已创作】\n" + "\n".join(lines))
        parts.append("请仅创作本首，不要续写或重复前面的诗作。")
        return "\n\n".join(parts)

    def _poem_progress_callback(
        self, state: SequenceState, index: int
    ) -> Callable[[dict[str, Any]], None]:
        """构造绑定到某首诗的进度回调.

        Args:
            state: 诗组状态。
            index: 诗序号。

        Returns:
            单参数进度回调。

        """

        def on_progress(info: dict[str, Any]) -> None:
            """把单首进度合并进诗组状态.

            Args:
                info: 单首流水线进度字典。

            """
            self._on_poem_progress(state, index, info)

        return on_progress

    def _on_poem_progress(
        self, state: SequenceState, index: int, info: dict[str, Any]
    ) -> None:
        """把单首进度合并进诗组状态并推送.

        Args:
            state: 诗组状态。
            index: 诗序号。
            info: 单首流水线进度字典。

        """
        poem = state.poems[index]
        draft = info.get("draft")
        if isinstance(draft, list):
            poem.draft = [str(x) for x in draft]
        title = info.get("title")
        if title:
            poem.final_title = str(title)
        rounds = info.get("refine_rounds")
        if isinstance(rounds, int):
            poem.rounds = rounds
        if "checker_pass" in info:
            poem.checker_pass = bool(info.get("checker_pass"))
        suggestions = info.get("checker_suggestions")
        if suggestions is not None:
            poem.checker_suggestions = str(suggestions)
        self._report(state)

    def _report(self, state: SequenceState) -> None:
        """推送诗组进度.

        Args:
            state: 诗组状态。

        """
        if self._on_progress:
            self._on_progress(
                {
                    "title": state.title,
                    "plan_text": state.plan_text,
                    "plan_completed": state.plan_completed,
                    "current_index": state.current_index,
                    "completed": state.completed,
                    "ok": state.ok,
                    "poems": [self._poem_dict(p) for p in state.poems],
                }
            )

    @staticmethod
    def _poem_dict(poem: SequencePoemState) -> dict[str, Any]:
        """把单首状态转为可序列化字典.

        Args:
            poem: 单首状态。

        Returns:
            字典形式。

        """
        return {
            "title": poem.final_title or poem.title,
            "planned_title": poem.title,
            "template_key": poem.template_key,
            "prompt": poem.prompt,
            "draft": list(poem.draft),
            "checker_pass": poem.checker_pass,
            "checker_suggestions": poem.checker_suggestions,
            "formatted_poem": poem.formatted_poem,
            "rounds": poem.rounds,
            "done": poem.done,
        }
