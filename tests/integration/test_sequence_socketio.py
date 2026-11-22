# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""SocketIO integration tests: sequence generate_sequence event, offline."""

import time
from typing import Any

import pytest

import app as app_module
from app import socketio
from src.pipeline.sequence import SequencePoemState, SequenceState


def _make_emitter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Intercept socketio.emit and collect emitted events.

    Args:
        monkeypatch: pytest monkeypatch instance.

    Returns:
        Captured (event, data) tuples.

    """
    emitted: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, data=None, to=None, **kw: emitted.append((event, data)),
    )
    return emitted


def _wait(emitted: list[tuple[str, Any]], name: str, timeout: float = 10.0) -> Any:
    """Wait until an event appears.

    Args:
        emitted: Captured events.
        name: Target event name.
        timeout: Timeout in seconds.

    Returns:
        Event data, or None on timeout.

    """
    done: Any = None
    for _ in range(int(timeout / 0.02)):
        time.sleep(0.02)
        for event, data in emitted:
            if event == name:
                done = data
        if done is not None:
            break
    return done


class _FakeSequence:
    """Fake pipeline returning a fixed sequence state."""

    last_keys: list[str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def run(
        self,
        topic: str,
        on_progress: Any = None,
        template_keys: list[str] | None = None,
    ) -> SequenceState:
        """Push one progress update and return the sequence result.

        Args:
            topic: Overall topic of the poem sequence.
            on_progress: Progress callback.
            template_keys: Per-poem meter keys chosen by the user.

        Returns:
            The fixed sequence state.

        """
        type(self).last_keys = template_keys
        if on_progress:
            on_progress(
                {
                    "title": "总题",
                    "plan_text": "计划",
                    "plan_completed": True,
                    "current_index": 0,
                    "completed": False,
                    "ok": False,
                    "poems": [],
                }
            )
        return SequenceState(
            topic=topic,
            title="总题",
            plan_text="计划",
            plan_completed=True,
            completed=True,
            ok=True,
            poems=[
                SequencePoemState(
                    title="其一",
                    template_key="zh_wujue",
                    prompt="写春",
                    draft=["句"],
                    final_title="其一",
                    formatted_poem="句。",
                    checker_pass=True,
                    done=True,
                )
            ],
        )


def test_generate_sequence_emits_progress_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_sequence pushes progress/done events and forwards template_keys."""
    monkeypatch.setattr("src.pipeline.sequence.PoemSequencePipeline", _FakeSequence)
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit(
        "generate_sequence",
        {"topic": "四季", "template_keys": ["zh_wujue", "zh_rumengling"]},
    )
    done = _wait(emitted, "sequence_done")

    assert done is not None
    assert done["ok"] is True
    assert done["title"] == "总题"
    assert done["poems"][0]["title"] == "其一"
    assert _FakeSequence.last_keys == ["zh_wujue", "zh_rumengling"]
    assert any(event == "sequence_progress" for event, _ in emitted)


def test_generate_sequence_empty_topic_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push an error when the sequence topic is empty."""
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit("generate_sequence", {"topic": ""})
    errors = [data for event, data in emitted if event == "error"]
    assert errors
    assert "must not be empty" in str(errors[0])


def test_generate_sequence_empty_template_keys_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push an error when template_keys is empty."""
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit("generate_sequence", {"topic": "四季", "template_keys": []})
    errors = [data for event, data in emitted if event == "error"]
    assert errors
    assert "Select a meter" in str(errors[0])


def test_generate_sequence_exception_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push an error when the sequence pipeline raises."""

    class _Boom:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run(
            self,
            topic: str,
            on_progress: Any = None,
            template_keys: list[str] | None = None,
        ) -> SequenceState:
            raise RuntimeError("boom")

    monkeypatch.setattr("src.pipeline.sequence.PoemSequencePipeline", _Boom)
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit("generate_sequence", {"topic": "四季"})
    error = _wait(emitted, "error")
    assert error is not None
    assert "Sequence generation failed" in str(error)
