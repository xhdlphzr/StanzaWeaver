# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""SocketIO 集成测试：用桩 LLM 驱动 generate 事件，验证进度/定稿推送。

不发起真实网络请求；emit 被替换为录制器，便于断言推送的事件。
"""

import time
from typing import Any

import pytest

import app as app_module
from app import socketio
from src.agents import checker_ai, writer_ai
from tests.helpers import make_stub, tool_call

DESC = "SocketIO 测试主题"
DRAFT = "床前明月光\n疑是地上霜\n举头望明月\n低头思故乡"
REVISED_LINE = "窗前明月光"


def _make_emitter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    emitted: list[tuple[str, object]] = []
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, data=None, to=None, **kw: emitted.append((event, data)),
    )
    return emitted


def _patch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    writer_stub = make_stub(
        stream=[DESC, DRAFT],
        chat=[
            tool_call("refine_line", {"line": 0, "new_text": REVISED_LINE}),
            tool_call("submit", {}),
        ],
    )
    checker_stub = make_stub(chat=[tool_call("submit", {"pass": True})])
    monkeypatch.setattr(writer_ai, "LLMClient", writer_stub)
    monkeypatch.setattr(checker_ai, "LLMClient", checker_stub)


def test_generate_emits_progress_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm(monkeypatch)
    emitted = _make_emitter(monkeypatch)

    client = socketio.test_client(app_module.app)
    client.emit("generate", {"topic": "静夜思", "template_key": "zh_wujue"})

    done = None
    for _ in range(300):
        time.sleep(0.05)
        for event, data in emitted:
            if event == "done":
                done = data
        if done is not None:
            break

    events = {e for e, _ in emitted}
    assert "progress" in events
    assert done is not None
    assert done["checker_pass"] is True
    assert done["final_poem"][0] == REVISED_LINE


def test_generate_empty_input_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _make_emitter(monkeypatch)
    client = socketio.test_client(app_module.app)
    client.emit("generate", {"topic": "", "template_key": ""})
    errors = [d for e, d in emitted if e == "error"]
    assert errors
    assert "不能为空" in str(errors[0])
