# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

from openai import OpenAI


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
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
            import json

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
        response = self.client.chat.completions.create(**kwargs)
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
                        "arguments": __import__("json").dumps(
                            tc["arguments"], ensure_ascii=False
                        ),
                    },
                }
                for tc in response["tool_calls"]
            ]
        return msg
