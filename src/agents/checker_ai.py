# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""检查 AI：句意终审。

对诗歌做语义评审（句意通顺、语义契合；中文 8 行以上附加对仗检查），
通过 submit 工具返回 pass/suggestions。
"""

import json
from typing import Any

from ..tools import CHECKER_TOOLS
from .base import LLMClient, Message

CheckResult = dict[str, Any]


def _build_checker_system(
    description: str, poem: list[str], template: dict[str, Any]
) -> str:
    """构造检查 AI 的系统提示。

    Args:
        description: 主题描述。
        poem: 诗行列表。
        template: 模板字典。

    Returns:
        系统提示文本。
    """
    parallelism_note = ""
    dim_count = 2
    if template.get("name") in ("五言律诗", "七言律诗"):
        parallelism_note = """
3. **对仗检查**: 检查颔联（第3-4行）和颈联（第5-6行）是否存在词性、结构上的对仗关系。句式结构应两两对应（如: 名词对名词、动词对动词、偏正对偏正）。若对仗明显不当或缺失，务必指出具体问题。"""
        dim_count = 3

    return (
        f"""你是一位严格的诗歌评审专家。请从以下{dim_count}个维度审阅诗歌，并给出结论。

【主题描述】
{description}

【诗歌文本】
"""
        + "\n".join(f"  [{i}] {line}" for i, line in enumerate(poem))
        + f"""

【评审维度】
1. **句意通顺**: 每行诗文在语义上是否通顺、自然，有无语病、逻辑断裂或意象割裂。
2. **语义契合**: 全诗意象是否统一，情感和意境是否与主题描述相符，用词是否恰当，有无违和之处。{parallelism_note}

请调用 submit 工具给出评审结论:
- pass: true 表示所有{dim_count}个检查维度全部通过
- pass: false 表示任一维度存在问题，必须在 suggestions 中按维度逐条说明具体问题和修改建议"""
    )


class CheckerAI:
    """句意终审代理（独立 LLM 端点/模型）。"""

    def __init__(self, config: dict[str, Any]):
        """初始化检查 AI。

        Args:
            config: {"base_url", "api_key", "model"}。
        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def check(
        self,
        description: str,
        poem: list[str],
        template: dict[str, Any],
    ) -> CheckResult:
        """执行句意终审（最多重试 3 轮直到拿到 submit 结论）。

        Args:
            description: 主题描述。
            poem: 诗行列表。
            template: 模板字典。

        Returns:
            {"pass": bool, "suggestions": str}。
        """
        system_prompt = _build_checker_system(description, poem, template)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请对以上诗歌进行评审，按维度逐一检查后调用 submit 工具给出结论。",
            },
        ]

        try:
            for _ in range(3):
                response = self.client.chat(messages, tools=CHECKER_TOOLS)

                if response["tool_calls"]:
                    submit_args: dict[str, Any] | None = None
                    for tc in response["tool_calls"]:
                        if tc["name"] == "submit":
                            submit_args = tc["arguments"]
                            break
                    if submit_args is not None:
                        return {
                            "pass": bool(submit_args.get("pass", False)),
                            "suggestions": str(submit_args.get("suggestions", "")),
                        }

                    messages.append(LLMClient.assistant_to_message(response))
                    messages.extend(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(
                                {
                                    "error": "请调用 submit 工具给出评审结论（pass 和 suggestions）。"
                                },
                                ensure_ascii=False,
                            ),
                        }
                        for tc in response["tool_calls"]
                    )
                    continue

                messages.append(LLMClient.assistant_to_message(response))
                messages.append(
                    {
                        "role": "user",
                        "content": "请务必调用 submit 工具给出评审结论（pass和suggestions）。",
                    }
                )
        except Exception as e:  # noqa: BLE001 - 终审兜底：任何调用失败转为"未通过+建议"
            return {"pass": False, "suggestions": f"检查AI调用失败: {e}"}

        return {"pass": False, "suggestions": "检查AI在多次尝试后未能给出结论"}
