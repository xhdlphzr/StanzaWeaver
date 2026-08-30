# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""agents 包单元测试：覆盖 src/agents 下全部代码（mock LLM 调用层，无真实网络）。"""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.agents.base import LLMClient, _is_loopback
from src.agents.checker_ai import CheckerAI, _build_checker_system
from src.agents.writer_ai import (
    WriterAI,
    _build_writer_system,
    _fire_stream,
)


def _msg(
    content: str = "", tool_calls: Any = None, reasoning: str | None = None
) -> Any:
    """构造 fake 的 OpenAI message 对象。

    Args:
        content: 消息文本。
        tool_calls: 工具调用列表。
        reasoning: 推理内容。

    Returns:
        模拟 OpenAI message 的 SimpleNamespace 对象。
    """
    return SimpleNamespace(
        content=content, tool_calls=tool_calls, reasoning_content=reasoning
    )


def _resp(message: Any) -> Any:
    """构造 fake 的 chat.completions.create 返回值（含 choices[0].message）。

    Args:
        message: 模拟 message 对象。

    Returns:
        包装后的 ChatResult 对象。
    """
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tc(name: str, args_json: str, tid: str = "1") -> Any:
    """构造 fake 的 tool_call 对象（arguments 为 JSON 字符串）。

    Args:
        name: 工具名称。
        args_json: JSON 格式的工具参数字符串。
        tid: 调用 ID。

    Returns:
        模拟 tool_call 的 SimpleNamespace 对象。
    """
    return SimpleNamespace(
        id=tid, function=SimpleNamespace(name=name, arguments=args_json)
    )


def _chunk(content: str) -> Any:
    """构造流式 chunk（含 delta.content）。

    Args:
        content: 文本块内容。

    Returns:
        模拟流式 chunk 的 SimpleNamespace 对象。
    """
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


def _chunk_empty() -> Any:
    """构造空 delta 的流式 chunk。

    Returns:
        choices 为空列表的 SimpleNamespace 对象。
    """
    return SimpleNamespace(choices=[])


def _make_llm(base_url: str) -> tuple[LLMClient, MagicMock]:
    """构造 LLMClient（OpenAI 被 mock），返回 (client, mock_httpx_client)。

    Args:
        base_url: API 基础地址。

    Returns:
        (client, mock_httpx_client) 元组。
    """
    with patch("src.agents.base.OpenAI", MagicMock()):
        c = LLMClient(base_url, "k", "m")
    client = MagicMock()
    object.__setattr__(c, "client", cast(Any, client))
    client.base_url = base_url
    return c, client


# --------------------------------------------------------------------------- #
# _is_loopback
# --------------------------------------------------------------------------- #
def test_is_loopback_true() -> None:
    """回环地址（127.0.0.1 / localhost / ::1）应返回 True。"""
    assert _is_loopback("http://127.0.0.1:11434/v1") is True
    assert _is_loopback("http://localhost:8000/v1") is True
    assert _is_loopback("http://[::1]:11434/v1") is True


def test_is_loopback_false() -> None:
    """非回环地址应返回 False。"""
    assert _is_loopback("https://api.openai.com/v1") is False
    assert _is_loopback("http://192.168.1.1/v1") is False


# --------------------------------------------------------------------------- #
# LLMClient.__init__ / _raise_with_hint
# --------------------------------------------------------------------------- #
def test_init_creates_http_client_for_loopback() -> None:
    """回环地址下应创建绕过代理的 httpx.Client（trust_env=False）。"""
    with patch("httpx.Client") as httpx_cls:
        httpx_cls.return_value = MagicMock(trust_env=False)
        _c, _ = _make_llm("http://127.0.0.1:11434/v1")
        httpx_cls.assert_called_once_with(trust_env=False)


def test_init_non_loopback_no_special_client() -> None:
    """非回环地址下正常初始化（不抛错，不创建 trust_env=False 的 client）。"""
    with patch("httpx.Client") as httpx_cls:
        _c, _ = _make_llm("https://api.openai.com/v1")
        httpx_cls.assert_not_called()


def test_raise_with_hint_loopback() -> None:
    """回环地址的错误应附带本地服务排障提示。"""
    c, _ = _make_llm("http://127.0.0.1:11434/v1")
    err = c._raise_with_hint(ValueError("boom"))
    assert isinstance(err, RuntimeError)
    assert "127.0.0.1" in str(err)


def test_raise_with_hint_non_loopback() -> None:
    """非回环地址的错误不附带本地提示。"""
    c, _ = _make_llm("https://api.openai.com/v1")
    err = c._raise_with_hint(ValueError("boom"))
    assert "127.0.0.1" not in str(err)


# --------------------------------------------------------------------------- #
# LLMClient.chat
# --------------------------------------------------------------------------- #
def test_chat_plain() -> None:
    """无工具的普通对话返回 content。"""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(return_value=_resp(_msg(content="你好")))
    res = c.chat([{"role": "user", "content": "x"}])
    assert res["content"] == "你好"
    assert res["tool_calls"] == []


def test_chat_with_tools_and_reasoning() -> None:
    """带工具调用且含 reasoning_content 时正确解析。"""
    c, client = _make_llm("https://api.openai.com/v1")
    msg = _msg(
        content="",
        tool_calls=[_tc("submit", json.dumps({"pass": True}))],
        reasoning="思考",
    )
    client.chat.completions.create = MagicMock(return_value=_resp(msg))
    res = c.chat([{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    assert res["reasoning_content"] == "思考"
    assert res["tool_calls"][0]["name"] == "submit"
    assert res["tool_calls"][0]["arguments"] == {"pass": True}


def test_chat_tool_call_invalid_json() -> None:
    """工具参数非法 JSON 时回退为空字典。"""
    c, client = _make_llm("https://api.openai.com/v1")
    msg = _msg(content="", tool_calls=[_tc("submit", "not-json")])
    client.chat.completions.create = MagicMock(return_value=_resp(msg))
    res = c.chat([{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    assert res["tool_calls"][0]["arguments"] == {}


def test_chat_raises() -> None:
    """底层调用抛错时包装为 RuntimeError。"""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(side_effect=RuntimeError("down"))
    with pytest.raises(RuntimeError):
        c.chat([{"role": "user", "content": "x"}])


# --------------------------------------------------------------------------- #
# LLMClient.chat_stream
# --------------------------------------------------------------------------- #
def test_chat_stream_collects() -> None:
    """流式对话逐 token 累积，空 delta 被跳过，on_chunk 被回调。"""
    c, client = _make_llm("https://api.openai.com/v1")
    chunks = [_chunk("a"), _chunk("b"), _chunk_empty()]
    client.chat.completions.create = MagicMock(return_value=chunks)
    seen: list[str] = []
    res = c.chat_stream(
        [{"role": "user", "content": "x"}], on_chunk=lambda t: seen.append(t)
    )
    assert res["content"] == "ab"
    assert seen == ["a", "ab"]


def test_chat_stream_no_callback() -> None:
    """无 on_chunk 时仅累积文本。"""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(return_value=[_chunk("xy")])
    res = c.chat_stream([{"role": "user", "content": "x"}])
    assert res["content"] == "xy"


def test_chat_stream_raises() -> None:
    """流式底层抛错时包装为 RuntimeError。"""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(side_effect=RuntimeError("down"))
    with pytest.raises(RuntimeError):
        c.chat_stream([{"role": "user", "content": "x"}])


# --------------------------------------------------------------------------- #
# LLMClient.assistant_to_message
# --------------------------------------------------------------------------- #
def test_assistant_to_message_full() -> None:
    """含 content / reasoning / tool_calls 时正确转换。"""
    resp = {
        "content": "诗",
        "reasoning_content": "思",
        "tool_calls": [{"id": "1", "name": "submit", "arguments": {"pass": True}}],
    }
    msg = LLMClient.assistant_to_message(resp)
    assert msg["content"] == "诗"
    assert msg["reasoning_content"] == "思"
    assert msg["tool_calls"][0]["function"]["name"] == "submit"


def test_assistant_to_message_no_content() -> None:
    """无 content 时 content 置 None。"""
    msg = LLMClient.assistant_to_message({"content": "", "tool_calls": []})
    assert msg["content"] is None


# --------------------------------------------------------------------------- #
# _fire_stream
# --------------------------------------------------------------------------- #
def test_fire_stream_normal() -> None:
    """回调正常时被调用。"""
    seen: list[str] = []
    _fire_stream(seen.append, "x")
    assert seen == ["x"]


def test_fire_stream_swallows_exception() -> None:
    """回调抛错时被吞掉，不中断主流程。"""

    def boom(_: str) -> None:
        raise ValueError("cb failed")

    _fire_stream(boom, "x")  # 不应抛出


# --------------------------------------------------------------------------- #
# _build_checker_system
# --------------------------------------------------------------------------- #
def test_build_checker_system_parallelism() -> None:
    """中文且 >=8 行时应包含对仗检查说明。"""
    text = _build_checker_system("主题", ["a", "b"], {"language": "zh", "lines": 8})
    assert "对仗" in text


def test_build_checker_system_no_parallelism() -> None:
    """非中文或不足 8 行时不包含对仗说明。"""
    text = _build_checker_system("主题", ["a"], {"language": "en", "lines": 4})
    assert "对仗" not in text


# --------------------------------------------------------------------------- #
# _build_writer_system
# --------------------------------------------------------------------------- #
def test_build_writer_system_with_template_obj() -> None:
    """提供含 describe 的模板对象时拼入完整格律描述。"""
    obj = SimpleNamespace(describe=lambda: "格律描述")
    text = _build_writer_system("主题", ["a"], {}, obj)
    assert "格律描述" in text


def test_build_writer_system_with_constraints() -> None:
    """无模板对象时按 syllable_constraints 逐位拼装约束文本。"""
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": [[{"onset": "zh", "nucleus": "a"}]],
    }
    text = _build_writer_system("主题", ["a", "b"], template)
    assert "声母=zh" in text
    assert "韵母=a" in text


def test_build_writer_system_with_coda_and_attributes() -> None:
    """syllable_constraints 含 coda 与 attributes 时拼装对应文本。"""
    template = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": [
            [
                {
                    "onset": "zh",
                    "nucleus": "a",
                    "coda": "ng",
                    "attributes": {"tone": "平"},
                }
            ]
        ],
    }
    text = _build_writer_system("主题", ["a"], template)
    assert "韵尾=ng" in text
    assert "tone=平" in text


def test_build_writer_system_with_feedback() -> None:
    """带 feedback 时拼装反馈段落。"""
    text = _build_writer_system(
        "主题", ["a"], {"language": "zh", "lines": 1}, feedback="请更婉约"
    )
    assert "请更婉约" in text


# --------------------------------------------------------------------------- #
# CheckerAI
# --------------------------------------------------------------------------- #
def _make_checker() -> tuple[CheckerAI, MagicMock]:
    """创建 CheckerAI 用于测试（OpenAI 被 mock）。

    Returns:
        (checker, mock_chat) 元组。
    """
    with patch("src.agents.base.OpenAI", MagicMock()):
        checker = CheckerAI(
            {"base_url": "http://127.0.0.1:11434/v1", "api_key": "k", "model": "m"}
        )
    chat = MagicMock()
    object.__setattr__(checker, "client", cast(Any, chat))
    return checker, chat


def test_checker_pass_true() -> None:
    """submit 返回 pass=True 时通过。"""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [{"id": "1", "name": "submit", "arguments": {"pass": True}}],
    }
    res = checker.check("主题", ["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is True


def test_checker_pass_false() -> None:
    """submit 返回 pass=False 时附带建议。"""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [
            {
                "id": "1",
                "name": "submit",
                "arguments": {"pass": False, "suggestions": "改"},
            }
        ],
    }
    res = checker.check("主题", ["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert res["suggestions"] == "改"


def test_checker_tool_calls_no_submit() -> None:
    """有工具调用但无 submit 时追加提示并继续，直至 3 轮后放弃。"""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [{"id": "1", "name": "search", "arguments": {}}],
    }
    res = checker.check("主题", ["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert "未能给出结论" in res["suggestions"]


def test_checker_no_tool_calls() -> None:
    """模型未调用工具时追加提醒，3 轮后放弃。"""
    checker, chat = _make_checker()
    chat.chat.return_value = {"content": "我看看", "tool_calls": []}
    res = checker.check("主题", ["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False


def test_checker_exception_fallback() -> None:
    """调用抛错时兜底为未通过。"""
    checker, chat = _make_checker()
    chat.chat.side_effect = RuntimeError("boom")
    res = checker.check("主题", ["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert "boom" in res["suggestions"]


# --------------------------------------------------------------------------- #
# WriterAI.generate_description
# --------------------------------------------------------------------------- #
def _make_writer() -> tuple[WriterAI, MagicMock]:
    """创建 WriterAI 用于测试（OpenAI 被 mock）。

    Returns:
        (writer, mock_chat) 元组。
    """
    with patch("src.agents.base.OpenAI", MagicMock()):
        writer = WriterAI(
            {"base_url": "http://127.0.0.1:11434/v1", "api_key": "k", "model": "m"}
        )
    chat = MagicMock()
    object.__setattr__(writer, "client", cast(Any, chat))
    return writer, chat


def test_generate_description_stream() -> None:
    """带 on_stream 时走 chat_stream。"""
    writer, chat = _make_writer()
    chat.chat_stream.return_value = {"content": "描述文本", "tool_calls": []}
    desc, detail = writer.generate_description("主题", on_stream=lambda t: None)
    assert desc == "描述文本"
    assert detail == "描述文本"


def test_generate_description_plain() -> None:
    """无 on_stream 时走普通 chat。"""
    writer, chat = _make_writer()
    chat.chat.return_value = {"content": "描述文本", "tool_calls": []}
    desc, _ = writer.generate_description("主题")
    assert desc == "描述文本"


# --------------------------------------------------------------------------- #
# WriterAI.generate_draft
# --------------------------------------------------------------------------- #
def test_generate_draft_template_obj_describe() -> None:
    """提供模板对象时使用其 describe() 生成约束描述。"""
    from src.templates.zh import WujueTemplate

    writer, chat = _make_writer()
    chat.chat.return_value = {"content": "一二三四五\n六七八九十", "tool_calls": []}
    poem, _ = writer.generate_draft(
        "主题", {"language": "zh", "lines": 2}, WujueTemplate()
    )
    assert len(poem) == 2


def test_generate_draft_retry_wrong_lines_then_syllables() -> None:
    """行数不对→重试；音节数不对→重试；最终通过。"""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        {"content": "一行", "tool_calls": []},
        {"content": "一二三四五\n一二三四", "tool_calls": []},
        {"content": "一二三四五\n六七八九十", "tool_calls": []},
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    poem, _ = writer.generate_draft("主题", template)
    assert len(poem) == 2


def test_generate_draft_stream_retry() -> None:
    """首轮走 chat_stream，其后走 chat，最终通过。"""
    writer, chat = _make_writer()
    chat.chat_stream.return_value = {"content": "一行", "tool_calls": []}
    chat.chat.return_value = {"content": "一二三四五\n六七八九十", "tool_calls": []}
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    poem, _ = writer.generate_draft("主题", template, on_stream=lambda t: None)
    assert len(poem) == 2


# --------------------------------------------------------------------------- #
# WriterAI.refine
# --------------------------------------------------------------------------- #
def _refine_seq(writer: WriterAI, seq: list[dict[str, Any]]) -> Any:
    """生成 refine_line 序列。

    Args:
        writer: WriterAI 实例。
        seq: 预置的 chat 返回值序列。

    Returns:
        配置好的 writer 实例。
    """
    writer.client.chat.side_effect = list(seq)  # type: ignore[attr-defined]
    return writer


def test_refine_no_tool_calls_then_submit() -> None:
    """无工具调用轮→提醒；随后 refine_line 修改；submit 提交。"""
    writer, _ = _make_writer()
    with patch(
        "src.agents.writer_ai.execute_refine_line", return_value={"poem": ["改"]}
    ):
        _refine_seq(
            writer,
            [
                {"content": "", "tool_calls": []},
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "name": "refine_line",
                            "arguments": {"line": 0, "new_text": "改"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "2", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
            ],
        )
        _, submitted, _, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}
        )
    assert submitted is True


def test_refine_submit_before_modification_rejected() -> None:
    """尚未修改即 submit 应被拒绝，之后修改再 submit 才通过。"""
    writer, _ = _make_writer()
    with patch(
        "src.agents.writer_ai.execute_refine_line", return_value={"poem": ["改"]}
    ):
        _refine_seq(
            writer,
            [
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "1", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "refine_line",
                            "arguments": {"line": 0, "new_text": "改"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "3", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
            ],
        )
        _, submitted, history, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}
        )
    assert submitted is True
    assert any(h["result"] == "rejected_no_changes" for h in history)


def test_refine_search_words_branch() -> None:
    """search_words 工具分支被处理并写入历史。"""
    writer, _ = _make_writer()
    with (
        patch(
            "src.agents.writer_ai.execute_search_words",
            return_value={"words": [{"word": "x"}]},
        ),
        patch(
            "src.agents.writer_ai.execute_refine_line", return_value={"poem": ["改"]}
        ),
    ):
        _refine_seq(
            writer,
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "name": "search_words",
                            "arguments": {"meaning": "春"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "refine_line",
                            "arguments": {"line": 0, "new_text": "改"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "3", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
            ],
        )
        _, _, history, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}, on_step=lambda _d: None
        )
    assert any(h["tool"] == "search_words" for h in history)


def test_refine_refine_line_error_branch() -> None:
    """refine_line 返回错误时记录失败详情；修正后再次提交通过。"""
    writer, _ = _make_writer()
    with patch(
        "src.agents.writer_ai.execute_refine_line",
        side_effect=[
            {"error": "行号越界"},
            {"poem": ["改"]},
        ],
    ):
        _refine_seq(
            writer,
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "name": "refine_line",
                            "arguments": {"line": 99, "new_text": "x"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "refine_line",
                            "arguments": {"line": 0, "new_text": "改"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "3", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
            ],
        )
        _, _, _, detail, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}
        )
    assert "失败" in detail


def test_refine_rewrite_branch() -> None:
    """rewrite 工具分支被处理并写入历史。"""
    writer, _ = _make_writer()
    with patch(
        "src.agents.writer_ai.execute_refine_line", return_value={"poem": ["改"]}
    ):
        # 注意: rewrite 分支内部会调用 _handle_rewrite -> generate_draft，
        # 额外消耗一次 self.client.chat（返回合法 1 行 5 音节诗稿）。
        _refine_seq(
            writer,
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "name": "rewrite",
                            "arguments": {"instruction": "更婉约"},
                        }
                    ],
                },
                {"content": "一二三四五", "tool_calls": []},  # _handle_rewrite 内部生成
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "refine_line",
                            "arguments": {"line": 0, "new_text": "改"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "3", "name": "submit", "arguments": {"pass": True}}
                    ],
                },
            ],
        )
        _, _, history, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}
        )
    assert any(h["tool"] == "rewrite" for h in history)


def test_refine_no_progress_guidance() -> None:
    """连续 3 轮无修改时注入空转引导提示（写入 messages）。"""
    writer, _ = _make_writer()
    template = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": None,
    }
    seq = [
        {
            "content": "",
            "tool_calls": [{"id": "1", "name": "search_words", "arguments": {}}],
        },
        {
            "content": "",
            "tool_calls": [{"id": "2", "name": "search_words", "arguments": {}}],
        },
        {
            "content": "",
            "tool_calls": [{"id": "3", "name": "search_words", "arguments": {}}],
        },
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "4",
                    "name": "refine_line",
                    "arguments": {"line": 0, "new_text": "改"},
                }
            ],
        },
        {
            "content": "",
            "tool_calls": [{"id": "5", "name": "submit", "arguments": {"pass": True}}],
        },
    ]
    captured: list[list[dict[str, Any]]] = []

    def fake_chat(messages: list[dict[str, Any]], tools: Any = None) -> dict[str, Any]:
        """捕获消息并按序返回预设响应。

        Args:
            messages: 对话消息列表。
            tools: 工具定义（忽略）。

        Returns:
            预设的响应字典。
        """
        captured.append(messages)
        return seq.pop(0)

    with (
        patch(
            "src.agents.writer_ai.execute_search_words",
            return_value={"words": [{"word": "x"}]},
        ),
        patch(
            "src.agents.writer_ai.execute_refine_line", return_value={"poem": ["改"]}
        ),
    ):
        writer.client.chat = fake_chat  # type: ignore[method-assign]
        _, submitted, _, _, _ = writer.refine(
            "主题", ["原"], template, on_stream=lambda _t: None
        )
    assert submitted is True
    joined = "\n".join(str(m.get("content", "")) for msgs in captured for m in msgs)
    assert "连续多轮" in joined


# --------------------------------------------------------------------------- #
# WriterAI._handle_rewrite
# --------------------------------------------------------------------------- #
def test_handle_rewrite_args_none() -> None:
    """args 为 None 时回退为空字典。"""
    writer, _ = _make_writer()
    writer.client.chat.side_effect = [  # type: ignore[attr-defined]
        {"content": "一行", "tool_calls": []},
        {"content": "一二三四五\n六七八九十", "tool_calls": []},
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    res = writer._handle_rewrite("主题", ["原"], template, args=None)
    assert "poem" in res


def test_handle_rewrite_with_template_obj_and_stream() -> None:
    """提供模板对象且带 on_stream 时走 describe 分支与 chat_stream。"""
    writer, chat = _make_writer()
    chat.chat_stream.return_value = {"content": "一行", "tool_calls": []}
    chat.chat.return_value = {"content": "一二三四五\n六七八九十", "tool_calls": []}
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    obj = SimpleNamespace(describe=lambda: "格律描述")
    res = writer._handle_rewrite(
        "主题",
        ["原"],
        template,
        template_obj=obj,
        args={"instruction": "更婉约"},
        on_stream=lambda _t: None,
    )
    assert "poem" in res


def test_handle_rewrite_with_template_obj_no_stream() -> None:
    """提供模板对象且无 on_stream 时走 describe 分支（chat 路径）。"""
    writer, _ = _make_writer()
    writer.client.chat.side_effect = [  # type: ignore[attr-defined]
        {"content": "一二三四五", "tool_calls": []},
    ]
    template = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": None,
    }
    obj = SimpleNamespace(describe=lambda: "格律描述")
    res = writer._handle_rewrite(
        "主题", ["原"], template, template_obj=obj, args={"instruction": "更婉约"}
    )
    assert "poem" in res


def test_handle_rewrite_validation_fail_then_pass() -> None:
    """重写校验未通过（行数正确但音节错）→ 重试；最终通过。"""
    writer, _ = _make_writer()
    writer.client.chat.side_effect = [  # type: ignore[attr-defined]
        {"content": "一二三四", "tool_calls": []},  # 1 行，但仅 4 音节，校验失败
        {"content": "一二三四五", "tool_calls": []},  # 合法
    ]
    template = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [5],
        "syllable_constraints": None,
    }
    res = writer._handle_rewrite("主题", ["原"], template)
    assert "poem" in res
