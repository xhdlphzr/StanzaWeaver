# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""LLM invocation wrapper (OpenAI-compatible API).

- Loopback addresses (127.0.0.1/localhost) bypass shell proxies automatically
  (trust_env=False), fixing 502 Bad Gateway from local services such as Ollama;
- Compatible with openai v3: its transport layer is based on ``httpx2``, so
  http_client is also passed an ``httpx2.Client``;
- chat/chat_stream support tool calls (Function Calling);
- Failures raise a RuntimeError that carries troubleshooting hints.
"""

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx2
import tiktoken
from openai import OpenAI

_LOCAL_HINTS = (
    "Please check: 1) the local service (e.g. Ollama) is running; "
    "2) Base URL includes /v1 (e.g. http://127.0.0.1:11434/v1); "
    "3) the model is installed (ollama list)."
)

Message = dict[str, Any]
ToolCall = dict[str, Any]
ChatResult = dict[str, Any]
ChunkCallback = Callable[[str], None] | None


def _is_loopback(base_url: str) -> bool:
    """Check whether a URL is a loopback address.

    Args:
        base_url: LLM service address.

    Returns:
        True for a loopback address.

    """
    host = (urlparse(str(base_url)).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


class LLMClient:
    """OpenAI-compatible client (with proxy bypass and error hints)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        """Initialize the client.

        Args:
            base_url: Service address (local services must include /v1).
            api_key: API key.
            model: Model name.

        """
        http_client: httpx2.Client | None = None
        if _is_loopback(base_url):
            http_client = httpx2.Client(trust_env=False)
        self.client = OpenAI(
            base_url=base_url, api_key=api_key, http_client=http_client
        )
        self.model = model

    def _raise_with_hint(self, e: Exception) -> RuntimeError:
        """Build an exception carrying troubleshooting hints.

        Args:
            e: Original exception.

        Returns:
            RuntimeError (with troubleshooting hints for local services).

        """
        hint = _LOCAL_HINTS if _is_loopback(str(self.client.base_url)) else ""
        return RuntimeError(
            f"LLM call failed (base_url={self.client.base_url}, "
            f"model={self.model}): {e}" + (f" {hint}" if hint else "")
        )

    def chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> ChatResult:
        """Run a non-streaming chat completion (optionally with tools).

        Args:
            messages: Message list.
            tools: OpenAI tool schema list (optional).

        Returns:
            {"role", "content", "tool_calls": [...]}.

        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise self._raise_with_hint(e) from e
        choice = response.choices[0]
        msg = choice.message

        result: ChatResult = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [],
        }

        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            result["reasoning_content"] = reasoning

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result["tool_calls"].append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    }
                )

        return result

    def chat_stream(
        self, messages: list[Message], on_chunk: ChunkCallback = None
    ) -> ChatResult:
        """Run a streaming chat completion: accumulate tokens and call back.

        Args:
            messages: Message list.
            on_chunk: Callback after each delta (passed the full accumulated text).

        Returns:
            {"role": "assistant", "content": full text, "tool_calls": []}.

        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise self._raise_with_hint(e) from e
        full_content = ""
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.content:
                full_content += delta.content
                if on_chunk:
                    on_chunk(full_content)
        return {"role": "assistant", "content": full_content, "tool_calls": []}

    def count_tokens(self, messages: list[Message]) -> int:
        """Estimate the token count of a message list.

        Uses a tiktoken encoder to count the tokens of all message contents.

        Args:
            messages: Message list.

        Returns:
            Estimated total token count.

        """
        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            content = msg.get("content")
            if content:
                total += len(encoding.encode(str(content)))
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    total += len(encoding.encode(json.dumps(tc, ensure_ascii=False)))
            total += 4
        return total

    @staticmethod
    def assistant_to_message(response: ChatResult) -> Message:
        """Convert a ChatResult into a continuation assistant message.

        Args:
            response: Return value of chat/chat_stream.

        Returns:
            OpenAI message format (with function arguments when tool calls exist).

        """
        msg: Message = {"role": "assistant"}
        if response.get("content"):
            msg["content"] = response["content"]
        else:
            msg["content"] = None
        if response.get("reasoning_content"):
            msg["reasoning_content"] = response["reasoning_content"]
        if response.get("tool_calls"):
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in response["tool_calls"]
            ]
        return msg
