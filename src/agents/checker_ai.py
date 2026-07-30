# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from .base import LLMClient
from ..tools import CHECKER_TOOLS


def _build_checker_system(description: str, poem: list[str], template: dict) -> str:
    language = template.get("language", "zh")
    lines = template.get("lines", len(poem))

    parallelism_note = ""
    dim_count = 2
    if language == "zh" and lines >= 8:
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
    def __init__(self, config: dict):
        self.client = LLMClient(
            base_url=config["base_url"],
            api_key=config["api_key"],
            model=config["model"],
        )

    def check(
        self,
        description: str,
        poem: list[str],
        template: dict,
    ) -> dict:
        system_prompt = _build_checker_system(description, poem, template)
        messages = [
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
                    for tc in response["tool_calls"]:
                        if tc["name"] == "submit":
                            args = tc["arguments"]
                            return {
                                "pass": args.get("pass", False),
                                "suggestions": args.get("suggestions", ""),
                            }

                messages.append(LLMClient.assistant_to_message(response))
                messages.append(
                    {
                        "role": "user",
                        "content": "请务必调用 submit 工具给出评审结论（pass和suggestions）。",
                    }
                )
        except Exception as e:
            return {"pass": False, "suggestions": f"检查AI调用失败: {e}"}

        return {"pass": False, "suggestions": "检查AI在多次尝试后未能给出结论"}
