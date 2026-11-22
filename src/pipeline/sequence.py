# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Poem-sequence pipeline: plan, generate/check poem by poem, aggregate.

Step 1 has the SequenceArchitect plan the sequence title and each poem's meter
and creative requirements. Step 2 runs each poem in order in its own session,
reusing the single-poem PoetryPipeline (description, first draft, line
refinement, checker AI final review) and injecting the sequence goal and the
already finished poems into the current poem. The results are aggregated once
all poems finish. Cross-poem consistency relies on planning and injection; no
separate symbolic check is performed for the whole sequence.
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
    """Generation state of one poem in the sequence."""

    title: str
    template_key: str
    prompt: str
    language: str = ""
    centered: bool = True
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
    """Complete state of one sequence generation."""

    topic: str = ""
    title: str = ""
    plan_text: str = ""
    plan_completed: bool = False
    poems: list[SequencePoemState] = field(default_factory=list)
    current_index: int = 0
    completed: bool = False
    ok: bool = False


class PoemSequencePipeline:
    """Poem-sequence pipeline: architect planning, per-poem pipeline, aggregation."""

    def __init__(
        self,
        writer_config: dict[str, Any] | None = None,
        checker_config: dict[str, Any] | None = None,
    ):
        """Initialize the poem-sequence pipeline.

        Args:
            writer_config: Writer/architect AI config (defaults to the global
                config).
            checker_config: Checker AI config (defaults to the global config).

        """
        config = get_config()
        self.writer_config = writer_config or config.writer
        self.checker_config = checker_config or config.checker
        self.architect: SequenceArchitect | None = None
        self._on_progress: ProgressCallback = None

    def _get_architect(self) -> SequenceArchitect:
        """Get the architect (initialized lazily).

        Returns:
            SequenceArchitect instance.

        """
        if self.architect is None:
            self.architect = SequenceArchitect(self.writer_config)
        return self.architect

    def _make_poem_pipeline(self) -> PoetryPipeline:
        """Create a single-poem pipeline (easy to replace in tests).

        Returns:
            PoetryPipeline instance.

        """
        return PoetryPipeline(self.writer_config, self.checker_config)

    def run(
        self,
        topic: str,
        on_progress: ProgressCallback = None,
        max_rounds: int = 12,
        template_keys: list[str] | None = None,
    ) -> SequenceState:
        """Run sequence generation.

        Args:
            topic: Overall sequence goal.
            on_progress: Progress callback.
            max_rounds: Maximum planning rounds.
            template_keys: User-fixed meter keys for each poem; when provided,
                the architect no longer adds poems and only sets the sequence
                title and per-poem creative requirements.

        Returns:
            Final sequence state.

        Raises:
            ValueError: template_keys is empty or contains an unknown template.

        """
        self._on_progress = on_progress
        catalog = list_dicts()
        seed: list[SequencePoemPlan] | None = None
        if template_keys is not None:
            if not template_keys:
                raise ValueError("A poem sequence needs at least one poem")
            seed = []
            for index, key in enumerate(template_keys, 1):
                try:
                    get_template(key)
                except KeyError as exc:
                    raise ValueError(f"Unknown meter template key: {key}") from exc
                seed.append(SequencePoemPlan(title=f"Poem {index}", template_key=key))
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
                    title=p.title,
                    template_key=p.template_key,
                    prompt=p.prompt,
                    language=get_template(p.template_key).language,
                    centered=get_template(p.template_key).centered,
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
        """Build the generation instruction for the poem at ``index``.

        The instruction combines the overall goal, this poem's requirements, and
        a summary of previous poems.

        Args:
            state: Sequence state.
            index: Poem index (0-based).

        Returns:
            Instruction text used as the single-poem pipeline topic.

        """
        poem = state.poems[index]
        tpl = get_template(poem.template_key)
        parts = [
            f"[Sequence goal] {state.topic}",
            f"[Sequence title] {state.title}",
            f"[This poem's requirements] {poem.prompt}",
            (
                f"[This poem's meter] {tpl.name} ({tpl.language}, "
                f"{tpl.lines} lines)\n{tpl.describe()}"
            ),
        ]
        previous = state.poems[:index]
        if previous:
            lines: list[str] = []
            for number, prev in enumerate(previous, 1):
                first_line = prev.draft[0] if prev.draft else "(unfinished)"
                title = prev.final_title or prev.title
                lines.append(f'Poem {number} "{title}" first line: {first_line}')
            parts.append("[Previously written]\n" + "\n".join(lines))
        parts.append("Write only this poem; do not continue or repeat earlier poems.")
        return "\n\n".join(parts)

    def _poem_progress_callback(
        self, state: SequenceState, index: int
    ) -> Callable[[dict[str, Any]], None]:
        """Build a progress callback bound to one poem.

        Args:
            state: Sequence state.
            index: Poem index.

        Returns:
            A single-argument progress callback.

        """

        def on_progress(info: dict[str, Any]) -> None:
            """Merge single-poem progress into the sequence state.

            Args:
                info: Single-poem pipeline progress dict.

            """
            self._on_poem_progress(state, index, info)

        return on_progress

    def _on_poem_progress(
        self, state: SequenceState, index: int, info: dict[str, Any]
    ) -> None:
        """Merge single-poem progress into the sequence state and push it.

        Args:
            state: Sequence state.
            index: Poem index.
            info: Single-poem pipeline progress dict.

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
        formatted = info.get("formatted_poem")
        if formatted is not None:
            poem.formatted_poem = str(formatted)
        self._report(state)

    def _report(self, state: SequenceState) -> None:
        """Push sequence progress.

        Args:
            state: Sequence state.

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
        """Convert single-poem state to a serializable dictionary.

        Args:
            poem: Single-poem state.

        Returns:
            Dictionary form.

        """
        return {
            "title": poem.final_title or poem.title,
            "planned_title": poem.title,
            "template_key": poem.template_key,
            "language": poem.language,
            "centered": poem.centered,
            "prompt": poem.prompt,
            "draft": list(poem.draft),
            "checker_pass": poem.checker_pass,
            "checker_suggestions": poem.checker_suggestions,
            "formatted_poem": poem.formatted_poem,
            "rounds": poem.rounds,
            "done": poem.done,
        }
