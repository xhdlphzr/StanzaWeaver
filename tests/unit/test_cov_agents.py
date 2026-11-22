# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the agents package (LLM layer mocked, no real network)."""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.agents.base import LLMClient, _is_loopback
from src.agents.checker_ai import CheckerAI, _build_checker_system
from src.agents.writer_ai import (
    WriterAI,
    _build_draft_system,
    _build_refine_system,
    _fire_stream,
)


def _msg(
    content: str = "", tool_calls: Any = None, reasoning: str | None = None
) -> Any:
    """Build a fake OpenAI message object.

    Args:
        content: Message text.
        tool_calls: Tool call list.
        reasoning: Reasoning content.

    Returns:
        SimpleNamespace object mimicking an OpenAI message.

    """
    return SimpleNamespace(
        content=content, tool_calls=tool_calls, reasoning_content=reasoning
    )


def _resp(message: Any) -> Any:
    """Build a fake chat.completions.create result (with choices[0].message).

    Args:
        message: Simulated message object.

    Returns:
        Wrapped ChatResult object.

    """
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tc(name: str, args_json: str, tid: str = "1") -> Any:
    """Build a fake tool_call object (arguments is a JSON string).

    Args:
        name: Tool name.
        args_json: Tool arguments as a JSON string.
        tid: Call ID.

    Returns:
        SimpleNamespace object mimicking a tool_call.

    """
    return SimpleNamespace(
        id=tid, function=SimpleNamespace(name=name, arguments=args_json)
    )


def _chunk(content: str) -> Any:
    """Build a streaming chunk (with delta.content).

    Args:
        content: Chunk text content.

    Returns:
        SimpleNamespace object mimicking a streaming chunk.

    """
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


def _chunk_empty() -> Any:
    """Build a streaming chunk with an empty delta.

    Returns:
        SimpleNamespace object whose choices is an empty list.

    """
    return SimpleNamespace(choices=[])


def _make_llm(base_url: str) -> tuple[LLMClient, MagicMock]:
    """Build an LLMClient (OpenAI mocked) and its mock HTTP client.

    Args:
        base_url: API base URL.

    Returns:
        (client, mock_httpx_client) tuple.

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
    """Verify loopback addresses (127.0.0.1 / localhost / ::1) return True."""
    assert _is_loopback("http://127.0.0.1:11434/v1") is True
    assert _is_loopback("http://localhost:8000/v1") is True
    assert _is_loopback("http://[::1]:11434/v1") is True


def test_is_loopback_false() -> None:
    """Verify non-loopback addresses return False."""
    assert _is_loopback("https://api.openai.com/v1") is False
    assert _is_loopback("http://192.168.1.1/v1") is False


# --------------------------------------------------------------------------- #
# LLMClient.__init__ / _raise_with_hint
# --------------------------------------------------------------------------- #
def test_init_creates_http_client_for_loopback() -> None:
    """Verify a loopback URL creates a proxy-bypassing httpx2.Client."""
    with patch("httpx2.Client") as httpx_cls:
        httpx_cls.return_value = MagicMock(trust_env=False)
        _c, _ = _make_llm("http://127.0.0.1:11434/v1")
        httpx_cls.assert_called_once_with(trust_env=False)


def test_init_non_loopback_no_special_client() -> None:
    """Verify non-loopback URLs initialize without a trust_env=False client."""
    with patch("httpx2.Client") as httpx_cls:
        _c, _ = _make_llm("https://api.openai.com/v1")
        httpx_cls.assert_not_called()


def test_raise_with_hint_loopback() -> None:
    """Verify loopback errors include a local-service troubleshooting hint."""
    c, _ = _make_llm("http://127.0.0.1:11434/v1")
    err = c._raise_with_hint(ValueError("boom"))
    assert isinstance(err, RuntimeError)
    assert "127.0.0.1" in str(err)


def test_raise_with_hint_non_loopback() -> None:
    """Verify non-loopback errors carry no local hint."""
    c, _ = _make_llm("https://api.openai.com/v1")
    err = c._raise_with_hint(ValueError("boom"))
    assert "127.0.0.1" not in str(err)


# --------------------------------------------------------------------------- #
# LLMClient.chat
# --------------------------------------------------------------------------- #
def test_chat_plain() -> None:
    """Verify a plain chat without tools returns content."""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(return_value=_resp(_msg(content="你好")))
    res = c.chat([{"role": "user", "content": "x"}])
    assert res["content"] == "你好"
    assert res["tool_calls"] == []


def test_chat_with_tools_and_reasoning() -> None:
    """Verify tool calls and reasoning_content parse correctly."""
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
    """Verify invalid tool JSON falls back to an empty dict."""
    c, client = _make_llm("https://api.openai.com/v1")
    msg = _msg(content="", tool_calls=[_tc("submit", "not-json")])
    client.chat.completions.create = MagicMock(return_value=_resp(msg))
    res = c.chat([{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    assert res["tool_calls"][0]["arguments"] == {}


def test_chat_raises() -> None:
    """Verify underlying errors are wrapped as RuntimeError."""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(side_effect=RuntimeError("down"))
    with pytest.raises(RuntimeError):
        c.chat([{"role": "user", "content": "x"}])


# --------------------------------------------------------------------------- #
# LLMClient.chat_stream
# --------------------------------------------------------------------------- #
def test_chat_stream_collects() -> None:
    """Verify tokens accumulate, empty deltas are skipped and on_chunk fires."""
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
    """Verify text accumulates when no on_chunk is given."""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(return_value=[_chunk("xy")])
    res = c.chat_stream([{"role": "user", "content": "x"}])
    assert res["content"] == "xy"


def test_chat_stream_raises() -> None:
    """Verify stream errors are wrapped as RuntimeError."""
    c, client = _make_llm("https://api.openai.com/v1")
    client.chat.completions.create = MagicMock(side_effect=RuntimeError("down"))
    with pytest.raises(RuntimeError):
        c.chat_stream([{"role": "user", "content": "x"}])


# --------------------------------------------------------------------------- #
# LLMClient.count_tokens
# --------------------------------------------------------------------------- #
def test_count_tokens_basic() -> None:
    """Verify count_tokens returns a positive integer."""
    c, _ = _make_llm("https://api.openai.com/v1")
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    tokens = c.count_tokens(msgs)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_tokens_with_tool_calls() -> None:
    """Verify messages with tool_calls count toward tokens."""
    c, _ = _make_llm("https://api.openai.com/v1")
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "name": "submit", "arguments": {"pass": True}}],
        }
    ]
    tokens = c.count_tokens(msgs)
    assert tokens > 0


def test_count_tokens_empty() -> None:
    """Verify an empty message list still returns a small token count."""
    c, _ = _make_llm("https://api.openai.com/v1")
    tokens = c.count_tokens([])
    assert tokens == 0


def test_count_tokens_unknown_model_fallback() -> None:
    """Verify an unknown model hits KeyError and falls back to cl100k_base."""
    c, _ = _make_llm("https://api.openai.com/v1")
    c.model = "totally_unknown_model_xyz"
    msgs = [{"role": "user", "content": "hello"}]
    tokens = c.count_tokens(msgs)
    assert tokens > 0


# --------------------------------------------------------------------------- #
# LLMClient.assistant_to_message
# --------------------------------------------------------------------------- #
def test_assistant_to_message_full() -> None:
    """Verify content, reasoning and tool_calls convert correctly."""
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
    """Verify missing content becomes None."""
    msg = LLMClient.assistant_to_message({"content": "", "tool_calls": []})
    assert msg["content"] is None


# --------------------------------------------------------------------------- #
# _fire_stream
# --------------------------------------------------------------------------- #
def test_fire_stream_normal() -> None:
    """Verify a normal callback is invoked."""
    seen: list[str] = []
    _fire_stream(seen.append, "x")
    assert seen == ["x"]


def test_fire_stream_swallows_exception() -> None:
    """Verify a callback exception is swallowed and does not interrupt."""

    def boom(_: str) -> None:
        raise ValueError("cb failed")

    _fire_stream(boom, "x")  # Must not raise


# --------------------------------------------------------------------------- #
# _build_checker_system
# --------------------------------------------------------------------------- #
def test_build_checker_system_parallelism() -> None:
    """Verify regulated-verse templates include the antithesis check note."""
    text = _build_checker_system(
        ["a", "b"], {"name": "五言律诗", "language": "zh", "lines": 8}
    )
    assert "对仗" in text


def test_build_checker_system_no_parallelism() -> None:
    """Verify non-Chinese or under-8-line templates omit the antithesis note."""
    text = _build_checker_system(["a"], {"language": "en", "lines": 4})
    assert "对仗" not in text


def test_build_checker_system_includes_user_prompt_and_rule() -> None:
    """Verify the checker prompt includes user prompt, rule note and feedback."""
    text = _build_checker_system(
        ["a"],
        {"language": "zh", "lines": 4, "rule_note": "必须使用对仗句"},
        user_prompt="写一首思乡的七言绝句",
        user_feedback="再婉约一些",
    )
    assert "用户原始要求" in text
    assert "写一首思乡的七言绝句" in text
    assert "模板规则描述" in text
    assert "必须使用对仗句" in text
    assert "用户修改反馈" in text
    assert "再婉约一些" in text
    assert "用户要求符合" in text
    # The writer AI's distilled topic description is no longer used
    assert "【主题描述】" not in text


def test_build_checker_system_rule_description_fallback() -> None:
    """Verify rule_description fallback and that empty inputs add no section."""
    text = _build_checker_system(
        ["a"],
        {"language": "zh", "lines": 4, "rule_description": "格律说明"},
    )
    assert "模板规则描述" in text
    assert "格律说明" in text
    assert "\n【用户原始要求（创作提示词）】\n" not in text
    assert "\n【用户修改反馈（本轮必须落实）】\n" not in text

    no_rule = _build_checker_system(["a"], {"language": "zh", "lines": 4})
    assert "\n【模板规则描述】\n" not in no_rule


# --------------------------------------------------------------------------- #
# _build_draft_system / _build_refine_system
# --------------------------------------------------------------------------- #
def test_build_draft_system_basic() -> None:
    """Verify _build_draft_system includes language and meter description."""
    text = _build_draft_system("zh", "语言: zh\n行数: 4")
    assert "zh" in text
    assert "语言: zh\n行数: 4" in text


def test_build_refine_system_basic() -> None:
    """Verify _build_refine_system includes the meter description."""
    text = _build_refine_system("语言: zh\n行数: 4")
    assert "语言: zh\n行数: 4" in text


def test_build_refine_system_with_feedback() -> None:
    """Verify _build_refine_system adds a feedback section when given."""
    text = _build_refine_system("语言: zh\n行数: 4", feedback="请更婉约")
    assert "请更婉约" in text


# --------------------------------------------------------------------------- #
# CheckerAI
# --------------------------------------------------------------------------- #
def _make_checker() -> tuple[CheckerAI, MagicMock]:
    """Create a CheckerAI for tests (OpenAI mocked).

    Returns:
        (checker, mock_chat) tuple.

    """
    with patch("src.agents.base.OpenAI", MagicMock()):
        checker = CheckerAI(
            {"base_url": "http://127.0.0.1:11434/v1", "api_key": "k", "model": "m"}
        )
    chat = MagicMock()
    object.__setattr__(checker, "client", cast(Any, chat))
    return checker, chat


def test_checker_pass_true() -> None:
    """Verify submit with pass=True passes."""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [{"id": "1", "name": "submit", "arguments": {"pass": True}}],
    }
    res = checker.check(["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is True


def test_checker_pass_false() -> None:
    """Verify submit with pass=False returns suggestions."""
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
    res = checker.check(["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert res["suggestions"] == "改"


def test_checker_tool_calls_no_submit() -> None:
    """Verify tool calls without submit retry, then give up after 3 rounds."""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [{"id": "1", "name": "search", "arguments": {}}],
    }
    res = checker.check(["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert "did not return a verdict" in res["suggestions"]


def test_checker_no_tool_calls() -> None:
    """Verify a model that calls no tools is reminded, then dropped."""
    checker, chat = _make_checker()
    chat.chat.return_value = {"content": "我看看", "tool_calls": []}
    res = checker.check(["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False


def test_checker_check_sends_user_prompt_to_llm() -> None:
    """Verify check puts user prompt/feedback into the system message."""
    checker, chat = _make_checker()
    chat.chat.return_value = {
        "content": "",
        "tool_calls": [{"id": "1", "name": "submit", "arguments": {"pass": True}}],
    }
    res = checker.check(
        ["line"],
        {"language": "zh", "lines": 4, "rule_note": "模板规则"},
        user_prompt="用户原始提示词",
        user_feedback="请更婉约",
    )
    assert res["pass"] is True
    messages = chat.chat.call_args[0][0]
    system = messages[0]["content"]
    assert "用户原始提示词" in system
    assert "模板规则" in system
    assert "请更婉约" in system


def test_checker_exception_fallback() -> None:
    """Verify call errors fall back to not passing."""
    checker, chat = _make_checker()
    chat.chat.side_effect = RuntimeError("boom")
    res = checker.check(["line"], {"language": "zh", "lines": 4})
    assert res["pass"] is False
    assert "boom" in res["suggestions"]


# --------------------------------------------------------------------------- #
# WriterAI.generate_description
# --------------------------------------------------------------------------- #
def _make_writer() -> tuple[WriterAI, MagicMock]:
    """Create a WriterAI for tests (OpenAI mocked).

    Returns:
        (writer, mock_chat) tuple.

    """
    with patch("src.agents.base.OpenAI", MagicMock()):
        writer = WriterAI(
            {"base_url": "http://127.0.0.1:11434/v1", "api_key": "k", "model": "m"}
        )
    chat = MagicMock()
    chat.count_tokens.return_value = 0
    object.__setattr__(writer, "client", cast(Any, chat))
    return writer, chat


def test_generate_description_stream() -> None:
    """Verify on_stream routes through chat_stream."""
    writer, chat = _make_writer()
    chat.chat_stream.return_value = {"content": "描述文本", "tool_calls": []}
    msgs: list[dict[str, Any]] = []
    desc = writer.generate_description("主题", msgs, on_stream=lambda t: None)
    assert desc == "描述文本"


def test_generate_description_plain() -> None:
    """Verify no on_stream routes through plain chat."""
    writer, chat = _make_writer()
    chat.chat.return_value = {"content": "描述文本", "tool_calls": []}
    msgs: list[dict[str, Any]] = []
    desc = writer.generate_description("主题", msgs)
    assert desc == "描述文本"


# --------------------------------------------------------------------------- #
# WriterAI.generate_draft
# --------------------------------------------------------------------------- #
def test_generate_draft_template_obj_describe() -> None:
    """Verify a template object supplies its describe() constraint text."""
    from src.templates.zh import WujueTemplate

    writer, chat = _make_writer()
    chat.chat.return_value = {
        "content": "一二三四五\n六七八九十",
        "tool_calls": [
            {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
        ],
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft(
        "主题", {"language": "zh", "lines": 2}, msgs, WujueTemplate()
    )
    assert len(poem) == 2


def test_generate_draft_submit_wrong_lines_then_retry() -> None:
    """Verify a wrong line count retries, then passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First submit: wrong line count
        {
            "content": "一行",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "标题"}}
            ],
        },
        # Second submit: correct
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "2", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_stream_retry() -> None:
    """Verify the on_stream callback fires."""
    writer, chat = _make_writer()
    chat.chat.return_value = {
        "content": "一二三四五\n六七八九十",
        "tool_calls": [
            {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
        ],
    }
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    fired: list[str] = []
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft(
        "主题", template, msgs, on_stream=lambda t: fired.append(t)
    )
    assert len(poem) == 2
    assert any("thinking" in f for f in fired)


def test_generate_draft_submit_poem_arg_and_bad_punct() -> None:
    """Verify submit replaces the poem; bad punctuation retries."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "name": "submit",
                    "arguments": {
                        "title": "标题",
                        "poem": ["一二三四五", "六七八九十"],
                        "punctuation": ["。"],
                    },
                }
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "2",
                    "name": "submit",
                    "arguments": {
                        "title": "标题",
                        "poem": ["一二三四五", "六七八九十"],
                        "punctuation": ["。", "。", "。"],
                    },
                }
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "3",
                    "name": "submit",
                    "arguments": {
                        "title": "标题",
                        "poem": ["一二三四五", "六七八九十"],
                        "punctuation": ["，", "。"],
                    },
                }
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, punct, _ = writer.generate_draft("主题", template, msgs)
    assert poem == ["一二三四五", "六七八九十"]
    assert punct == ["，", "。"]


# --------------------------------------------------------------------------- #
# WriterAI.refine
# --------------------------------------------------------------------------- #
def _refine_seq(writer: WriterAI, seq: list[dict[str, Any]]) -> Any:
    """Install a preset chat response sequence.

    Args:
        writer: WriterAI instance.
        seq: Preset chat return value sequence.

    Returns:
        The configured writer instance.

    """
    writer.client.chat.side_effect = list(seq)  # type: ignore[attr-defined]
    return writer


def test_refine_no_tool_calls_then_submit() -> None:
    """Verify a no-tool round is reminded, then modify and submit run."""
    writer, _ = _make_writer()
    with patch("src.agents.writer_ai.execute_modify", return_value={"poem": ["改"]}):
        _refine_seq(
            writer,
            [
                {"content": "", "tool_calls": []},
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "name": "modify",
                            "arguments": {
                                "modify_type": "line",
                                "line": 0,
                                "content": "改",
                            },
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
        msgs: list[dict[str, Any]] = []
        _, _, _, _, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}, msgs
        )


def test_refine_submit_without_modification_allowed() -> None:
    """Verify submitting without modification is now allowed."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {"id": "1", "name": "submit", "arguments": {"pass": True}}
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, _, rounds, _title, _punct = writer.refine(
        "主题", ["原"], {"language": "zh", "lines": 1}, msgs
    )
    assert poem == ["原"]
    assert rounds == 1
    assert any(h["tool"] == "submit" for h in history)


def test_refine_submit_rejected_when_meter_invalid() -> None:
    """Verify invalid submit is rejected with errors until meter passes."""
    from src.prosody.meter_validator import ValidationResult

    class _SeqValidator:
        """Fake validator returning preset results in order.

        Args:
            results: ValidationResults returned by validate in order.

        """

        def __init__(self, results: list[ValidationResult]) -> None:
            self._results = list(results)

        def validate(
            self, poem: list[str], template: dict[str, Any], template_obj: Any = None
        ) -> ValidationResult:
            return self._results.pop(0)

    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {"title": "测试"},
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "submit",
                        "arguments": {"title": "测试"},
                    }
                ],
            },
        ],
    )
    writer.validator = cast(
        Any,
        _SeqValidator(
            [
                ValidationResult(passed=False, errors=["第1行不匹配"]),
                ValidationResult(passed=True),
            ]
        ),
    )
    msgs: list[dict[str, Any]] = []
    poem, history, detail, rounds, _title, _punct = writer.refine(
        "主题", ["原"], {"language": "zh", "lines": 1}, msgs
    )
    assert poem == ["原"]
    assert rounds == 2
    submits = [h for h in history if h["tool"] == "submit"]
    assert len(submits) == 2
    # First submit rejected by full validation; second passes
    assert submits[0]["result"] == {"error": ["第1行不匹配"]}
    assert submits[1]["result"] == "submitted"
    assert "rejected" in detail
    assert "第1行不匹配" in detail


def test_refine_submit_gate_end_to_end() -> None:
    """Verify real quatrain: invalid submit rejected, then modify fixes it."""
    valid_first_line = "远岸栖云树"
    # Opposition broken (line 1, syllable 2 made level), so the poem is invalid
    invalid_poem = ["西窗残月冷", "溪流伴月明", "桃红迷柳岸", "古道远山风"]
    valid_poem = [valid_first_line, "溪流伴月明", "桃红迷柳岸", "古道远山风"]
    template = {
        "name": "五言绝句",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    from src.templates.zh import WujueTemplate

    tpl = WujueTemplate()

    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {"title": "测试"},
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "modify",
                        "arguments": {
                            "modify_type": "line",
                            "line": 0,
                            "content": valid_first_line,
                        },
                    }
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, detail, rounds, _title, _punct = writer.refine(
        "主题", invalid_poem, template, msgs, tpl
    )
    assert poem == valid_poem
    assert rounds == 2
    submits = [h for h in history if h["tool"] == "submit"]
    assert len(submits) == 1
    # Invalid full meter check rejects submit and returns the errors
    assert "error" in submits[0]["result"]
    assert "rejected" in detail
    refines = [h for h in history if h["tool"] == "modify"]
    assert len(refines) == 1
    assert "poem" in refines[0]["result"]


def test_refine_modify_validation_errors_recorded() -> None:
    """Verify modify records validation_errors after a failed meter check."""
    invalid_first_line = "西窗残月冷"
    valid_first_line = "远岸栖云树"
    initial_poem = ["远岫依烟岭", "溪流伴月明", "桃红迷柳岸", "古道远山风"]
    template = {
        "name": "五言绝句",
        "language": "zh",
        "lines": 4,
        "syllables_per_line": [5, 5, 5, 5],
        "syllable_constraints": None,
    }
    from src.templates.zh import WujueTemplate

    tpl = WujueTemplate()

    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "modify",
                        "arguments": {
                            "modify_type": "line",
                            "line": 0,
                            "content": invalid_first_line,
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "modify",
                        "arguments": {
                            "modify_type": "line",
                            "line": 0,
                            "content": valid_first_line,
                        },
                    }
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, detail, _rounds, _title, _punct = writer.refine(
        "主题", initial_poem, template, msgs, tpl
    )
    assert poem == [valid_first_line, "溪流伴月明", "桃红迷柳岸", "古道远山风"]
    refines = [h for h in history if h["tool"] == "modify"]
    assert len(refines) == 2
    # The first modify fails full validation -> validation_errors recorded
    assert "validation_errors" in refines[0]["result"]
    assert "meter issues" in detail


def test_refine_search_words_branch() -> None:
    """Verify the search_words branch is handled and recorded in history."""
    writer, _ = _make_writer()
    with (
        patch(
            "src.agents.writer_ai.execute_search_words",
            return_value={"words": [{"word": "x"}]},
        ),
        patch("src.agents.writer_ai.execute_modify", return_value={"poem": ["改"]}),
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
                            "arguments": {"query": "春"},
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "modify",
                            "arguments": {
                                "modify_type": "line",
                                "line": 0,
                                "content": "改",
                            },
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
        msgs: list[dict[str, Any]] = []
        _, history, _, _, _, _ = writer.refine(
            "主题",
            ["原"],
            {"language": "zh", "lines": 1},
            msgs,
            on_step=lambda _d: None,
        )
    assert any(h["tool"] == "search_words" for h in history)


def test_refine_modify_error_branch() -> None:
    """Verify modify errors are logged; a fixed retry then passes."""
    writer, _ = _make_writer()
    with patch(
        "src.agents.writer_ai.execute_modify",
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
                            "name": "modify",
                            "arguments": {
                                "modify_type": "line",
                                "line": 99,
                                "content": "x",
                            },
                        }
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "2",
                            "name": "modify",
                            "arguments": {
                                "modify_type": "line",
                                "line": 0,
                                "content": "改",
                            },
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
        msgs: list[dict[str, Any]] = []
        _, _, detail, _, _, _ = writer.refine(
            "主题", ["原"], {"language": "zh", "lines": 1}, msgs
        )
    assert "failed" in detail


def test_refine_modify_title_and_punctuation() -> None:
    """Verify modify title/punctuation branches update title and punctuation."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "modify",
                        "arguments": {"modify_type": "title", "content": "新标题"},
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "modify",
                        "arguments": {
                            "modify_type": "punctuation",
                            "content": ["，", "。"],
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {"id": "3", "name": "submit", "arguments": {"title": "终稿"}}
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, _, _, title, punct = writer.refine(
        "主题", ["原", "句"], {"language": "zh", "lines": 2}, msgs
    )
    assert title == "终稿"
    assert punct == ["，", "。"]
    assert poem == ["原", "句"]
    assert any(h["tool"] == "modify" for h in history)


def test_refine_submit_replaces_whole_poem_and_punctuation() -> None:
    """Verify submit replaces the whole poem and sets punctuation."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {
                            "title": "新标题",
                            "poem": ["新句一", "新句二"],
                            "punctuation": ["，", "。"],
                        },
                    }
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, _, _, title, punct = writer.refine(
        "主题", ["旧一", "旧二"], {"language": "zh", "lines": 2}, msgs
    )
    assert poem == ["新句一", "新句二"]
    assert title == "新标题"
    assert punct == ["，", "。"]
    assert any(h["tool"] == "submit" for h in history)


def test_refine_submit_punctuation_length_rejected() -> None:
    """Verify submit rejects a punctuation count that mismatches lines."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {
                            "title": "标题",
                            "punctuation": ["，"],
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "submit",
                        "arguments": {
                            "title": "标题",
                            "punctuation": ["，", "。"],
                        },
                    }
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    _, history, detail, _, _, punct = writer.refine(
        "主题", ["旧一", "旧二"], {"language": "zh", "lines": 2}, msgs
    )
    assert punct == ["，", "。"]
    submits = [h for h in history if h["tool"] == "submit"]
    assert any(
        isinstance(h["result"], dict) and "error" in h["result"] for h in submits
    )
    assert "punctuation marks" in detail


def test_refine_submit_punctuation_non_list_rejected() -> None:
    """Verify submit rejects non-list punctuation."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {"title": "标题", "punctuation": "，。"},
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {"id": "2", "name": "submit", "arguments": {"title": "标题"}}
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    _, history, detail, _, _, _ = writer.refine(
        "主题", ["旧一", "旧二"], {"language": "zh", "lines": 2}, msgs
    )
    submits = [h for h in history if h["tool"] == "submit"]
    assert any(
        isinstance(h["result"], dict) and "error" in h["result"] for h in submits
    )
    assert "Punctuation must be a list of strings" in detail


def test_refine_submit_poem_wrong_line_count_rejected() -> None:
    """Verify submit rejects a wrong line count, then accepts a valid poem."""
    writer, _ = _make_writer()
    _refine_seq(
        writer,
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "name": "submit",
                        "arguments": {
                            "title": "标题",
                            "poem": ["一", "二", "三"],
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "2",
                        "name": "submit",
                        "arguments": {
                            "title": "标题",
                            "poem": ["新一", "新二"],
                        },
                    }
                ],
            },
        ],
    )
    msgs: list[dict[str, Any]] = []
    poem, history, detail, _, _, _ = writer.refine(
        "主题", ["旧一", "旧二"], {"language": "zh", "lines": 2}, msgs
    )
    submits = [h for h in history if h["tool"] == "submit"]
    assert any("Line count mismatch" in str(h["result"]) for h in submits)
    assert "rejected" in detail
    assert poem == ["新一", "新二"]


def test_refine_no_progress_guidance() -> None:
    """Verify 3 no-progress rounds inject a guidance message."""
    writer, _ = _make_writer()
    template = {
        "language": "zh",
        "lines": 1,
        "syllables_per_line": [1],
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
                    "name": "modify",
                    "arguments": {"modify_type": "line", "line": 0, "content": "改"},
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
        """Capture messages and return preset responses in order.

        Args:
            messages: Conversation message list.
            tools: Tool definitions (ignored).

        Returns:
            Preset response dict.

        """
        captured.append(messages)
        return seq.pop(0)

    with (
        patch(
            "src.agents.writer_ai.execute_search_words",
            return_value={"words": [{"word": "x"}]},
        ),
        patch("src.agents.writer_ai.execute_modify", return_value={"poem": ["改"]}),
    ):
        writer.client.chat = fake_chat  # type: ignore[method-assign]
        msgs: list[dict[str, Any]] = []
        _, _, _, rounds, _, _ = writer.refine(
            "主题", ["原"], template, msgs, on_stream=lambda _t: None
        )
    assert rounds >= 1
    joined = "\n".join(str(m.get("content", "")) for msgs in captured for m in msgs)
    assert "连续多轮" in joined


# --------------------------------------------------------------------------- #
# Token compression
# --------------------------------------------------------------------------- #
def test_check_and_compress_no_op_below_threshold() -> None:
    """Verify no compression below the token threshold."""
    writer, chat = _make_writer()
    chat.count_tokens.return_value = 100
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "test"}]
    writer._check_and_compress(msgs, "desc", ["poem"], {"language": "zh", "lines": 1})
    assert len(msgs) == 1


def test_check_and_compress_triggers_at_threshold() -> None:
    """Verify compression triggers at the token threshold."""
    from src.agents.writer_ai import COMPRESS_THRESHOLD

    writer, chat = _make_writer()
    chat.count_tokens.return_value = COMPRESS_THRESHOLD
    chat.chat.return_value = {"content": "压缩摘要", "tool_calls": []}
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "old message"}]
    writer._check_and_compress(msgs, "desc", ["诗稿"], {"language": "zh", "lines": 1})
    assert len(msgs) == 2
    assert "压缩摘要" in str(msgs[0]["content"])
    assert "诗稿" in str(msgs[1]["content"])


# --------------------------------------------------------------------------- #
# Coverage gaps: _extract_poem_from_messages, generate_draft branches
# --------------------------------------------------------------------------- #
def test_extract_poem_from_messages_finds_assistant() -> None:
    """Verify poem lines are extracted from assistant messages."""
    from src.agents.writer_ai import _extract_poem_from_messages

    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "行一\n行二\n行三"},
    ]
    result = _extract_poem_from_messages(msgs)
    assert result == ["行一", "行二", "行三"]


def test_extract_poem_from_messages_empty() -> None:
    """Verify no assistant message returns an empty list."""
    from src.agents.writer_ai import _extract_poem_from_messages

    msgs: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
    result = _extract_poem_from_messages(msgs)
    assert result == []


def test_generate_draft_submit_empty_content_fallback() -> None:
    """Verify an empty submit content falls back to history extraction."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: AI returns empty content plus a submit tool call
        {
            "content": "",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    # Pre-write one assistant message for the fallback extraction
    msgs.append({"role": "assistant", "content": "一二三四五\n六七八九十"})
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_submit_syllable_fail_then_pass() -> None:
    """Verify correct lines but wrong syllables retries, then passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: line count correct but syllables wrong
        {
            "content": "一二三四\n五六七八",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "标题"}}
            ],
        },
        # Second: correct
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "2", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_no_tool_calls_retry() -> None:
    """Verify no tool call retries, then submit passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: no tool_calls
        {"content": "一二三四五\n六七八九十", "tool_calls": []},
        # Second: submit
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_no_tool_calls_wrong_lines_retry() -> None:
    """Verify no tool call plus wrong lines retries, then passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: wrong line count
        {"content": "一二三四五", "tool_calls": []},
        # Second: correct submit
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_no_tool_calls_syllable_fail_retry() -> None:
    """Verify no tool call plus wrong syllables retries, then passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: line count correct but syllables wrong
        {"content": "一二三四\n五六七八", "tool_calls": []},
        # Second: correct submit
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "1", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, _title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2


def test_generate_draft_empty_title_retry() -> None:
    """Verify an empty submit title retries, then passes."""
    writer, chat = _make_writer()
    chat.chat.side_effect = [
        # First: empty title
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [{"id": "1", "name": "submit", "arguments": {"title": ""}}],
        },
        # Second: correct
        {
            "content": "一二三四五\n六七八九十",
            "tool_calls": [
                {"id": "2", "name": "submit", "arguments": {"title": "测试标题"}}
            ],
        },
    ]
    template = {
        "language": "zh",
        "lines": 2,
        "syllables_per_line": [5, 5],
        "syllable_constraints": None,
    }
    msgs: list[dict[str, Any]] = []
    poem, title, _punct, _ = writer.generate_draft("主题", template, msgs)
    assert len(poem) == 2
    assert title == "测试标题"


# --------------------------------------------------------------------------- #
# format_poem (Chinese templates)
# --------------------------------------------------------------------------- #
def test_format_poem_wujue() -> None:
    """Verify five-character quatrain format: one line each, commas/periods."""
    from src.templates.zh import WujueTemplate

    t = WujueTemplate()
    result = t.format_poem(
        ["静夜思", "白日依山尽", "黄河入海流", "欲穷千里目", "更上一层楼"]
    )
    assert result.startswith("静夜思\n")
    assert "白日依山尽，" in result
    assert "黄河入海流。" in result
    assert "更上一层楼。" in result


def test_format_poem_qijue() -> None:
    """Verify seven-character quatrain format: one line each, commas/periods."""
    from src.templates.zh import QijueTemplate

    t = QijueTemplate()
    result = t.format_poem(["登鹳雀楼", "白日依山尽黄河入海流", "欲穷千里目更上一层楼"])
    assert result.startswith("登鹳雀楼\n")
    assert "。" in result


def test_format_poem_wulv() -> None:
    """Verify five-character regulated verse: one couplet per line."""
    from src.templates.zh import WulvTemplate

    t = WulvTemplate()
    lines = ["标题", "句1", "句2", "句3", "句4", "句5", "句6", "句7", "句8"]
    result = t.format_poem(lines)
    assert result.startswith("标题\n")
    assert "句1，句2" in result
    assert "句7，句8。" in result


def test_format_poem_xiangjianhuan() -> None:
    """Verify Xiangjianhuan format: leading tab, stanza tab, default punctuation."""
    from src.templates.zh import XiangjianhuanTemplate

    t = XiangjianhuanTemplate()
    lines = ["标题", "上1", "上2", "上3", "下1", "下2", "下3", "下4"]
    result = t.format_poem(lines)
    assert result.startswith("标题\n\t")
    assert "\t" in result.split("\n")[1]
    assert "上1，上2。上3。" in result
    assert "下1，下2，下3。下4。" in result


def test_format_poem_qilv() -> None:
    """Verify seven-character regulated verse: one couplet per line."""
    from src.templates.zh import QilvTemplate

    t = QilvTemplate()
    lines = ["标题", "句1", "句2", "句3", "句4", "句5", "句6", "句7", "句8"]
    result = t.format_poem(lines)
    assert result.startswith("标题\n")
    assert "句1，句2" in result
    assert "句7，句8。" in result


def test_format_poem_qilv_odd_content() -> None:
    """Verify seven-character verse odd content lines hit the odd branch."""
    from src.templates.zh import QilvTemplate

    t = QilvTemplate()
    lines = ["标题", "句1", "句2", "句3"]
    result = t.format_poem(lines)
    assert result.startswith("标题\n")
    assert "句3。" in result


def test_format_poem_wulv_odd_content() -> None:
    """Verify five-character verse odd content lines hit the odd branch."""
    from src.templates.zh import WulvTemplate

    t = WulvTemplate()
    lines = ["标题", "句1", "句2", "句3"]
    result = t.format_poem(lines)
    assert result.startswith("标题\n")
    assert "句3。" in result


def test_format_poem_base() -> None:
    """Verify the base format_poem joins lines with newlines."""
    from src.templates.en import ShakespeareSonnetTemplate

    t = ShakespeareSonnetTemplate()
    result = t.format_poem(["title", "line1", "line2"])
    assert result == "title\nline1\nline2"


def test_format_poem_en_haiku() -> None:
    """Verify the English template uses the base newline-joining format_poem."""
    from src.templates.en import VillanelleTemplate

    t = VillanelleTemplate()
    result = t.format_poem(["spring", "cherry", "blossoms"])
    assert result == "spring\ncherry\nblossoms"


def test_format_poem_fr_haiku() -> None:
    """Verify the French template uses the base newline-joining format_poem."""
    from src.templates.fr import RondeauTemplate

    t = RondeauTemplate()
    result = t.format_poem(["printemps", "cerisier", "fleurs"])
    assert result == "printemps\ncerisier\nfleurs"


def test_format_poem_it_haiku() -> None:
    """Verify the Italian template uses the base format_poem newline join."""
    from src.templates.it import TerzaRimaTemplate

    t = TerzaRimaTemplate()
    result = t.format_poem(["primavera", "ciliegio", "fiori"])
    assert result == "primavera\nciliegio\nfiori"


def test_format_poem_la_elegy() -> None:
    """Verify the Latin template uses the base newline-joining format_poem."""
    from src.templates.la import HexameterTemplate

    t = HexameterTemplate()
    result = t.format_poem(["arma", "virumque", "cano"])
    assert result == "arma\nvirumque\ncano"


def test_format_poem_base_with_punctuation() -> None:
    """Verify the base format_poem applies punctuation line by line."""
    from src.templates.en import ShakespeareSonnetTemplate

    t = ShakespeareSonnetTemplate()
    result = t.format_poem(["title", "line1", "line2"], ["，", "。"])
    assert result == "title\nline1，\nline2。"


def test_format_poem_wulv_with_punctuation() -> None:
    """Verify five-character regulated verse joins couplets with punctuation."""
    from src.templates.zh import WulvTemplate

    t = WulvTemplate()
    lines = ["标题", "句1", "句2", "句3", "句4", "句5", "句6", "句7", "句8"]
    marks = ["，", "。", "，", "。", "，", "。", "，", "。"]
    result = t.format_poem(lines, marks)
    assert "句1，句2。" in result
    assert "句7，句8。" in result


def test_format_poem_wulv_with_punctuation_odd() -> None:
    """Verify odd content lines hit the odd branch with punctuation supplied."""
    from src.templates.zh import WulvTemplate

    t = WulvTemplate()
    result = t.format_poem(["标题", "句1", "句2", "句3"], ["，", "。", "。"])
    assert "句3。" in result


def test_format_poem_qilv_with_punctuation() -> None:
    """Verify seven-character regulated verse joins couplets with punctuation."""
    from src.templates.zh import QilvTemplate

    t = QilvTemplate()
    lines = ["标题", "句1", "句2", "句3", "句4", "句5", "句6", "句7", "句8"]
    marks = ["，", "。", "，", "。", "，", "。", "，", "。"]
    result = t.format_poem(lines, marks)
    assert "句1，句2。" in result


def test_format_poem_qilv_with_punctuation_odd() -> None:
    """Verify odd content lines hit the odd branch with punctuation supplied."""
    from src.templates.zh import QilvTemplate

    t = QilvTemplate()
    result = t.format_poem(["标题", "句1", "句2", "句3"], ["，", "。", "。"])
    assert "句3。" in result


def test_format_poem_xiangjianhuan_with_punctuation() -> None:
    """Verify Xiangjianhuan applies punctuation per line, then joins stanzas."""
    from src.templates.zh import XiangjianhuanTemplate

    t = XiangjianhuanTemplate()
    lines = ["标题", "上1", "上2", "上3", "下1", "下2", "下3", "下4"]
    marks = ["，", "，", "。", "，", "，", "，", "。"]
    result = t.format_poem(lines, marks)
    assert "\t" in result
    assert "上1，上2，上3。" in result


def test_format_poem_rumengling() -> None:
    """Verify Rumengling format: leading tab, single stanza, default punctuation."""
    from src.templates.zh import RumenglingTemplate

    t = RumenglingTemplate()
    lines = [
        "如梦令",
        "常记溪亭日暮",
        "沉醉不知归路",
        "兴尽晚回舟",
        "误入藕花深处",
        "争渡",
        "争渡",
        "惊起一滩鸥鹭",
    ]
    result = t.format_poem(lines)
    assert result.startswith("如梦令\n\t")
    assert "常记溪亭日暮，" in result
    assert "沉醉不知归路。" in result
    assert "争渡，争渡，" in result
    # Single stanza: no inter-stanza tab in the body (only the leading one)
    assert result.split("\n")[1].count("\t") == 1


def test_format_poem_langtaosha() -> None:
    """Verify Langtaosha format: leading tab, stanza tab, default punctuation."""
    from src.templates.zh import LangtaoshaTemplate

    t = LangtaoshaTemplate()
    lines = ["浪淘沙"] + [f"句{i}" for i in range(1, 11)]
    result = t.format_poem(lines)
    assert result.startswith("浪淘沙\n\t")
    assert result.split("\n")[1].count("\t") == 2
    assert "句1，句2。句3。句4，句5。" in result
    assert "句6，句7。句8。句9，句10。" in result


def test_format_poem_qingpingyue() -> None:
    """Verify Qingpingyue format: leading tab, stanza tab, default punctuation."""
    from src.templates.zh import QingpingyueTemplate

    t = QingpingyueTemplate()
    lines = ["清平乐"] + [f"句{i}" for i in range(1, 9)]
    result = t.format_poem(lines)
    assert result.startswith("清平乐\n\t")
    assert result.split("\n")[1].count("\t") == 2
    assert "句1，句2。句3，句4。" in result
    assert "句5，句6。句7，句8。" in result


def test_format_poem_langtaosha_with_punctuation() -> None:
    """Verify Langtaosha applies punctuation line by line."""
    from src.templates.zh import LangtaoshaTemplate

    t = LangtaoshaTemplate()
    lines = ["浪淘沙"] + [f"句{i}" for i in range(1, 11)]
    marks = ["，"] * 10
    result = t.format_poem(lines, marks)
    assert "句1，句2，句3，句4，句5，" in result
