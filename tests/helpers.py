# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""集成测试公共工具：桩 LLM 客户端（不实际访问 OpenAI）。

桩客户端按预置脚本返回 ChatResult，使 Pipeline / Flask / SocketIO 的集成
测试完全离线、可重复、无需网络。
"""

from typing import Any

from src.agents.base import ChatResult, LLMClient


def tool_call(name: str, arguments: dict[str, Any] | None = None) -> ChatResult:
    """构造一个带工具调用的助手消息（ChatResult）。

    Args:
        name: 工具名（如 "refine_line" / "submit"）。
        arguments: 工具参数。

    Returns:
        {"role", "content", "tool_calls": [{"id", "name", "arguments"}]}。
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
    """离线桩 LLM 客户端：按队列返回预置脚本，绝不发起网络请求。

    通过构造参数传入 ``stream_responses``（chat_stream 依次返回的文本）与
    ``chat_responses``（chat 依次返回的 ChatResult）。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        stream: list[str] | None = None,
        chat: list[ChatResult] | None = None,
    ):
        """仅记录连接参数，不创建真实 OpenAI 客户端。

        Args:
            base_url: API 基础地址。
            api_key: API 密钥。
            model: 模型名称。
            stream: chat_stream 依次返回的文本列表。
            chat: chat 依次返回的 ChatResult 列表。
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.stream_responses: list[str] = list(stream or [])
        self.chat_responses: list[ChatResult] = list(chat or [])
        self._stream_iter = iter(self.stream_responses)
        self._chat_iter = iter(self.chat_responses)

    def chat(self, messages: list[dict[str, Any]], tools: Any = None) -> ChatResult:
        """按序返回预置的 ChatResult；耗尽后返回空文本。

        Args:
            messages: 对话消息列表。
            tools: 工具定义（桩客户端忽略）。

        Returns:
            预置的 ChatResult。
        """
        try:
            return next(self._chat_iter)
        except StopIteration:
            return {"role": "assistant", "content": "", "tool_calls": []}

    def chat_stream(
        self, messages: list[dict[str, Any]], on_chunk: Any = None
    ) -> ChatResult:
        """按序返回预置文本（触发 on_chunk 回调）。

        Args:
            messages: 对话消息列表。
            on_chunk: 收到文本块时的回调函数。

        Returns:
            包含累积文本的 ChatResult。
        """
        try:
            text = next(self._stream_iter)
        except StopIteration:
            text = ""
        if on_chunk:
            on_chunk(text)
        return {"role": "assistant", "content": text, "tool_calls": []}

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """返回低 token 数以避免压缩触发（桩实现）。

        Args:
            messages: 消息列表（未使用）。

        Returns:
            固定返回 0（不触发压缩）。
        """
        return 0


def make_stub(
    stream: list[str] | None = None,
    chat: list[ChatResult] | None = None,
) -> type[StubLLMClient]:
    """生成预置脚本的桩客户端类。

    Args:
        stream: chat_stream 依次返回的文本列表。
        chat: chat 依次返回的 ChatResult 列表。

    Returns:
        可直接替换 WriterAI/CheckerAI 中 LLMClient 引用的子类。
    """
    script_stream = list(stream or [])
    script_chat = list(chat or [])

    class _Stub(StubLLMClient):
        """预置脚本的桩客户端（由 make_stub 动态生成）。"""

        def __init__(self, base_url: str, api_key: str, model: str) -> None:
            """调用父类 __init__ 并注入预置脚本。

            Args:
                base_url: 服务地址。
                api_key: API 密钥。
                model: 模型名称。
            """
            super().__init__(
                base_url, api_key, model, stream=script_stream, chat=script_chat
            )

    return _Stub
