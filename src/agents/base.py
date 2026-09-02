# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""LLM 调用封装（OpenAI 兼容接口）。

- 回环地址（127.0.0.1/localhost）自动绕过 shell 代理（trust_env=False），
  修复本地 Ollama 等服务的 502 Bad Gateway；
- chat/chat_stream 支持工具调用（Function Calling）；
- 失败时抛出带排查提示的 RuntimeError。
"""

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import tiktoken
from openai import OpenAI

_LOCAL_HINTS = (
    "请确认: 1) 本地服务(Ollama等)已启动; 2) Base URL 包含 /v1 "
    "(如 http://127.0.0.1:11434/v1); 3) 模型名已安装(ollama list)。"
)

Message = dict[str, Any]
ToolCall = dict[str, Any]
ChatResult = dict[str, Any]
ChunkCallback = Callable[[str], None] | None


def _is_loopback(base_url: str) -> bool:
    """判断 URL 是否为回环地址。

    Args:
        base_url: LLM 服务地址。

    Returns:
        回环地址返回 True。
    """
    host = (urlparse(str(base_url)).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


class LLMClient:
    """OpenAI 兼容客户端（含代理绕过与错误提示）。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        """初始化客户端。

        Args:
            base_url: 服务地址（本地服务须含 /v1）。
            api_key: API 密钥。
            model: 模型名。
        """
        http_client: httpx.Client | None = None
        if _is_loopback(base_url):
            http_client = httpx.Client(trust_env=False)
        self.client = OpenAI(
            base_url=base_url, api_key=api_key, http_client=http_client
        )
        self.model = model

    def _raise_with_hint(self, e: Exception) -> RuntimeError:
        """构造带排查提示的异常。

        Args:
            e: 原始异常。

        Returns:
            RuntimeError（本地服务附带排障提示）。
        """
        hint = _LOCAL_HINTS if _is_loopback(str(self.client.base_url)) else ""
        return RuntimeError(
            f"LLM 调用失败 (base_url={self.client.base_url}, model={self.model}): {e}"
            + (f" {hint}" if hint else "")
        )

    def chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> ChatResult:
        """非流式对话（可带工具）。

        Args:
            messages: 消息列表。
            tools: OpenAI 工具 Schema 列表（可选）。

        Returns:
            {"role", "content", "tool_calls": [...]}。
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
        """流式对话：逐 token 累积并回调。

        Args:
            messages: 消息列表。
            on_chunk: 每次增量后回调（参数为完整累积文本）。

        Returns:
            {"role": "assistant", "content": 完整文本, "tool_calls": []}。
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
        """估算消息列表的 token 数量。

        使用 tiktoken 编码器统计所有消息内容的 token 数。

        Args:
            messages: 消息列表。

        Returns:
            估算的 token 总数。
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
        """把 ChatResult 转为可继续对话的 assistant 消息。

        Args:
            response: chat/chat_stream 的返回。

        Returns:
            OpenAI 消息格式（含 tool_calls 时带 function 参数）。
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
