# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Pipeline 集成测试：用桩 LLM 客户端替代 OpenAI，验证四步流水线闭环。

不发起任何真实网络请求——描述/初稿/炼句/终审均由预置脚本驱动。
"""

import pytest

from src.agents import checker_ai, writer_ai
from src.pipeline.pipeline import PoetryPipeline
from tests.helpers import make_stub, tool_call

DESC = "测试主题：静夜思"
DRAFT = "床前明月光\n疑是地上霜\n举头望明月\n低头思故乡"
REVISED_LINE = "窗前明月光"


def _patch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入桩 LLM 客户端，使 Pipeline 完全离线运行。

    Args:
        monkeypatch: pytest monkeypatch 实例。
    """
    writer_stub = make_stub(
        stream=[DESC, DRAFT],
        chat=[
            # Step 2: generate_draft 用 submit 提交（content 包含诗稿）
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
            # Step 3: refine 第一轮 refine_line
            tool_call("refine_line", {"line": 0, "new_text": REVISED_LINE}),
            # Step 3: refine 提交（content 包含修改后的诗稿）
            {
                "role": "assistant",
                "content": REVISED_LINE + "\n" + "\n".join(DRAFT.split("\n")[1:]),
                "tool_calls": [
                    {
                        "id": "call_submit2",
                        "name": "submit",
                        "arguments": {"title": "静夜思"},
                    }
                ],
            },
        ],
    )
    checker_stub = make_stub(chat=[tool_call("submit", {"pass": True})])
    monkeypatch.setattr(writer_ai, "LLMClient", writer_stub)
    monkeypatch.setattr(checker_ai, "LLMClient", checker_stub)


def test_pipeline_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 pipeline full run。"""
    _patch_llm(monkeypatch)
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state = pipeline.run("静夜思", "zh_wujue")

    assert state.checker_pass is True
    assert state.title == "静夜思"
    assert state.final_poem == ["静夜思"] + state.draft
    # 炼句确实修改了首行
    assert state.draft[0] == REVISED_LINE
    # 炼句循环至少执行了「修改 + 提交」两步
    assert state.refine_rounds >= 2
    assert state.description == DESC


def test_pipeline_continue_with_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 pipeline continue with feedback。"""
    _patch_llm(monkeypatch)
    pipeline = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state = pipeline.run("静夜思", "zh_wujue")
    assert state.checker_pass is True

    # 用户反馈续跑：新建流水线（新的桩客户端迭代器）再次进入炼句并定稿
    pipeline2 = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state2 = pipeline2.continue_with_feedback(state, "请再婉约一些")
    assert state2.checker_pass is True
    assert state2.draft[0] == REVISED_LINE
