# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""SocketIO integration tests: a stub LLM drives the generate event.

No real network requests: emit is replaced by a recorder so pushed events
can be asserted.
"""

import time
from typing import Any

import pytest

import app as app_module
from app import socketio
from src.agents import checker_ai, writer_ai
from tests.helpers import make_stub, tool_call

DESC = "SocketIO 测试主题"
# Regulated five-character quatrain: valid tonal pattern, opposition, and rhyme.
DRAFT = "远岫依烟岭\n溪流伴月明\n桃红迷柳岸\n古道远山风"
REVISED_LINE = "远岸栖云树"


def _make_emitter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Build an event collector that intercepts all socketio.emit calls.

    Args:
        monkeypatch: pytest monkeypatch instance.

    Returns:
        A list of captured (event, data) tuples.

    """
    emitted: list[tuple[str, object]] = []
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, data=None, to=None, **kw: emitted.append((event, data)),
    )
    return emitted


def _patch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject stub LLM clients so the SocketIO flow runs fully offline.

    Args:
        monkeypatch: pytest monkeypatch instance.

    """
    writer_stub = make_stub(
        stream=[DESC, DRAFT],
        chat=[
            # Step 2: generate_draft submits (content holds the draft poem)
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
            # Step 3: first refine round modifies; passing full checks ends
            # refinement.
            tool_call(
                "modify",
                {"modify_type": "line", "line": 0, "content": REVISED_LINE},
            ),
        ],
    )
    checker_stub = make_stub(chat=[tool_call("submit", {"pass": True})])
    monkeypatch.setattr(writer_ai, "LLMClient", writer_stub)
    monkeypatch.setattr(checker_ai, "LLMClient", checker_stub)


def test_generate_emits_progress_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify generate emits progress and done events."""
    _patch_llm(monkeypatch)
    emitted = _make_emitter(monkeypatch)

    client = socketio.test_client(app_module.app)
    client.emit("generate", {"topic": "静夜思", "template_key": "zh_wujue"})

    done = None
    for _ in range(500):
        time.sleep(0.02)
        for event, data in emitted:
            if event == "done":
                done = data
        if done is not None:
            break

    events = {e for e, _ in emitted}
    assert "progress" in events
    assert done is not None
    assert done["checker_pass"] is True
    assert done["title"] == "静夜思"
    assert done["final_poem"][1] == REVISED_LINE


def test_generate_empty_input_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify generate rejects empty input."""
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)
    client.emit("generate", {"topic": "", "template_key": ""})
    errors = [d for e, d in emitted if e == "error"]
    assert errors
    assert "must not be empty" in str(errors[0])
