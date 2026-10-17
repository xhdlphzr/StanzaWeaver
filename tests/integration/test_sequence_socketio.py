# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""SocketIO 集成测试：诗组 generate_sequence 事件（离线，桩流水线）."""

import time
from typing import Any

import pytest

import app as app_module
from app import socketio
from src.pipeline.sequence import SequencePoemState, SequenceState


def _make_emitter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """拦截 socketio.emit 并收集事件.

    Args:
        monkeypatch: pytest monkeypatch 实例。

    Returns:
        收集到的 (event, data) 列表。

    """
    emitted: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, data=None, to=None, **kw: emitted.append((event, data)),
    )
    return emitted


def _wait(emitted: list[tuple[str, Any]], name: str, timeout: float = 10.0) -> Any:
    """等待某个事件出现.

    Args:
        emitted: 已收集事件。
        name: 目标事件名。
        timeout: 超时秒数。

    Returns:
        事件数据；超时返回 None。

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
    """返回预置诗组状态的假流水线."""

    last_keys: list[str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def run(
        self,
        topic: str,
        on_progress: Any = None,
        template_keys: list[str] | None = None,
    ) -> SequenceState:
        """推送一次进度并返回诗组结果.

        Args:
            topic: 诗组总目标。
            on_progress: 进度回调。
            template_keys: 用户固定的每首格律 key 列表。

        Returns:
            预置的诗组状态。

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
    """generate_sequence 推送 sequence_progress 与 sequence_done，并透传 template_keys."""
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
    """诗组主题为空时推送 error."""
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit("generate_sequence", {"topic": ""})
    errors = [data for event, data in emitted if event == "error"]
    assert errors
    assert "不能为空" in str(errors[0])


def test_generate_sequence_empty_template_keys_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """template_keys 为空时推送 error."""
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)

    client.emit("generate_sequence", {"topic": "四季", "template_keys": []})
    errors = [data for event, data in emitted if event == "error"]
    assert errors
    assert "至少" in str(errors[0])


def test_generate_sequence_exception_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """诗组流水线抛错时推送 error."""

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
    assert "诗组生成失败" in str(error)
