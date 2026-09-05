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
# 五言绝句（合律：二四相间/联内相对/联间相粘/二四行押平声韵）。
DRAFT = "远岫依烟岭\n溪流伴月明\n桃红迷柳岸\n古道远山风"
REVISED_LINE = "远岸栖云树"


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
            # Step 3: refine 第一轮 refine_line（修改后仍需通过全量格律校验）
            tool_call("refine_line", {"line": 0, "new_text": REVISED_LINE}),
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
    # 炼句确实修改了首行，且修改后通过全量格律校验（否则不会结束炼句）
    assert state.draft[0] == REVISED_LINE
    assert state.refine_rounds >= 1
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

    # 用户反馈续跑：新建流水线（新的桩客户端迭代器）再次进入炼句并定稿。
    # 当前诗稿已合律，续跑时模型直接 submit，submit 的全量校验同样通过。
    pipeline2 = PoetryPipeline(
        writer_config={"base_url": "x", "api_key": "x", "model": "x"},
        checker_config={"base_url": "x", "api_key": "x", "model": "x"},
    )
    state2 = pipeline2.continue_with_feedback(state, "请再婉约一些")
    assert state2.checker_pass is True
    assert state2.draft[0] == REVISED_LINE
