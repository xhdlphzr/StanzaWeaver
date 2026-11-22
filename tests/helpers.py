# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Shared integration-test helpers: a stub LLM client (no real OpenAI).

The stub client replays scripted responses as ChatResult, so integration tests
for Pipeline / Flask / SocketIO stay fully offline, repeatable, and network-free.
"""

from typing import Any

from src.agents.base import ChatResult, LLMClient


def tool_call(name: str, arguments: dict[str, Any] | None = None) -> ChatResult:
    """Build an assistant message with tool calls (ChatResult).

    Args:
        name: Tool name (e.g. "modify" / "submit").
        arguments: Tool arguments.

    Returns:
        {"role", "content", "tool_calls": [{"id", "name", "arguments"}]}.

    """
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": f"call_{name}",
                "name": name,
                "arguments": arguments if arguments is not None else {},
            }
        ],
    }


class StubLLMClient(LLMClient):
    """Offline stub LLM client: replays scripted responses, never hits the network.

    Pass ``stream_responses`` (texts returned by chat_stream in order) and
    ``chat_responses`` (ChatResults returned by chat in order) via the constructor.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        stream: list[str] | None = None,
        chat: list[ChatResult] | None = None,
    ):
        """Record connection parameters only; no real OpenAI client is created.

        Args:
            base_url: API base URL.
            api_key: API key.
            model: Model name.
            stream: Texts that chat_stream returns in order.
            chat: ChatResults that chat returns in order.

        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.stream_responses: list[str] = list(stream or [])
        self.chat_responses: list[ChatResult] = list(chat or [])
        self._stream_iter = iter(self.stream_responses)
        self._chat_iter = iter(self.chat_responses)

    def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> ChatResult:
        """Return scripted ChatResults in order; return empty text when exhausted.

        Args:
            messages: Conversation messages.
            tools: Tool definitions (ignored by the stub).

        Returns:
            A scripted ChatResult.

        """
        try:
            return next(self._chat_iter)
        except StopIteration:
            return {"role": "assistant", "content": "", "tool_calls": []}

    def chat_stream(
        self, messages: list[dict[str, Any]], on_chunk: Any = None
    ) -> ChatResult:
        """Return scripted text in order, invoking the on_chunk callback.

        Args:
            messages: Conversation messages.
            on_chunk: Callback invoked with each text chunk.

        Returns:
            A ChatResult containing the accumulated text.

        """
        try:
            text = next(self._stream_iter)
        except StopIteration:
            text = ""
        if on_chunk:
            on_chunk(text)
        return {"role": "assistant", "content": text, "tool_calls": []}

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Return a low token count so compression never triggers (stub).

        Args:
            messages: Message list (unused).

        Returns:
            Always 0, so compression never triggers.

        """
        return 0


def make_stub(
    stream: list[str] | None = None,
    chat: list[ChatResult] | None = None,
) -> type[StubLLMClient]:
    """Build a stub client class from scripted responses.

    Args:
        stream: Texts that chat_stream returns in order.
        chat: ChatResults that chat returns in order.

    Returns:
        A subclass that can replace the LLMClient used by WriterAI/CheckerAI.

    """
    script_stream = list(stream or [])
    script_chat = list(chat or [])

    class _Stub(StubLLMClient):
        """Scripted stub client (created dynamically by make_stub)."""

        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            """Call the parent __init__ and inject the scripted responses.

            Args:
                base_url: Service URL.
                api_key: API key.
                model: Model name.

            """
            super().__init__(
                base_url, api_key, model, stream=script_stream, chat=script_chat
            )

    return _Stub
