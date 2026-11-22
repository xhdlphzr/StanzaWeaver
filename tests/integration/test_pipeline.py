# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Pipeline integration tests: a stub LLM client replaces OpenAI.

Verifies the four-step pipeline end to end with no real network requests:
description/draft/refinement/final review are all scripted.
"""

import pytest

from src.agents import checker_ai, writer_ai
from src.pipeline.pipeline import PoetryPipeline
from tests.helpers import make_stub, tool_call

DESC = "测试主题：静夜思"
# Regulated five-character quatrain: valid tonal pattern, opposition, and rhyme.
DRAFT = "远岫依烟岭\n溪流伴月明\n桃红迷柳岸\n古道远山风"
REVISED_LINE = "远岸栖云树"


def _patch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject stub LLM clients so the pipeline runs fully offline.

    Args:
        monkeypatch: pytest monkeypatch instance.

    """
    writer_stub = make_stub(
        stream=[DESC, DRAFT],
        chat=[
            # Step 2: generate_draft submits via submit (content holds the poem)
            {
                "role": "assistant",
                "content": DRAFT,
                "tool_calls": [
                    {
                        "id": "call_submit",
                        "name": "submit",
                        "arguments": {"title": "静夜思"},
                    }
                ],
            },
            # Step 3: first refine round modifies (result must still pass meter)
            tool_call(
                "modify",
                {"modify_type": "line", "line": 0, "content": REVISED_LINE},
            ),
        ],
    )
    checker_stub = make_stub(chat=[tool_call("submit", {"pass": True})])
    monkeypatch.setattr(writer_ai, "LLMClient", writer_stub)
    monkeypatch.setattr(checker_ai, "LLMClient", checker_stub)


def test_pipeline_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a full pipeline run."""
    _patch_llm(monkeypatch)
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is True
    assert state.title == "静夜思"
    assert state.final_poem == ["静夜思"] + state.draft
    # Refinement changed the first line and the result still passes full meter
    # validation (otherwise refinement would not end).
    assert state.draft[0] == REVISED_LINE
    assert state.refine_rounds >= 1
    assert state.description == DESC


def test_pipeline_continue_with_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify pipeline continuation with feedback."""
    _patch_llm(monkeypatch)
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state = pipeline.run("静夜思", "zh_wujue")
    assert state.checker_pass is True

    # Continue with feedback: a new pipeline (fresh stub iterators) enters
    # refinement again and finalizes.
    # The draft is already valid, so the model submits directly and the full
    # submit validation passes too.
    pipeline2 = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state2 = pipeline2.continue_with_feedback(state, "请再婉约一些")
    assert state2.checker_pass is True
    assert state2.draft[0] == REVISED_LINE
