# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
from urllib.parse import urlparse

import httpx

from openai import OpenAI

_LOCAL_HINTS = (
    "请确认: 1) 本地服务(Ollama等)已启动; 2) Base URL 包含 /v1 "
    "(如 http://127.0.0.1:11434/v1); 3) 模型名已安装(ollama list)。"
)


def _is_loopback(base_url) -> bool:
    host = (urlparse(str(base_url)).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        http_client = None
        if _is_loopback(base_url):
            # 回环地址直连，绕过 shell 中的 HTTP(S)_PROXY 环境变量
            # (否则本地请求会被转发到代理，导致 502 Bad Gateway)
            http_client = httpx.Client(trust_env=False)
        self.client = OpenAI(
            base_url=base_url, api_key=api_key, http_client=http_client
        )
        self.model = model

    def _raise_with_hint(self, e: Exception) -> Exception:
        hint = _LOCAL_HINTS if _is_loopback(self.client.base_url) else ""
        return RuntimeError(
            f"LLM 调用失败 (base_url={self.client.base_url}, model={self.model}): {e}"
            + (f" {hint}" if hint else "")
        )

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs = {
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

        result = {
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

    def chat_stream(self, messages: list[dict], on_chunk: object = None) -> dict:
        kwargs = {
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

    @staticmethod
    def assistant_to_message(response: dict) -> dict:
        msg = {"role": "assistant"}
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
