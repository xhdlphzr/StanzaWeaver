# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""检查 AI：句意终审.

检查 AI 只依据**用户发给创作 AI 的原始提示词**与**模板规则描述**评审，
不使用创作 AI 自己提炼的主题描述，避免评审基准被模型的二次概括带偏；
用户最近的修改反馈（若有）也会一并提供，用于核对是否落实。

通过 submit 工具返回 pass/suggestions。
"""

import json
from typing import Any

from ..tools import CHECKER_TOOLS
from .base import LLMClient, Message

CheckResult = dict[str, Any]


def _template_rule_text(template: dict[str, Any]) -> str:
    """取模板的规则描述（优先用户填写的 rule_note，否则自动描述）.

    Args:
        template: 模板字典。

    Returns:
        规则描述文本；无则返回空串。

    """
    rule_note = str(template.get("rule_note", "") or "").strip()
    if rule_note:
        return rule_note
    return str(template.get("rule_description", "") or "").strip()


def _build_checker_system(
    poem: list[str],
    template: dict[str, Any],
    user_prompt: str = "",
    user_feedback: str = "",
) -> str:
    """构造检查 AI 的系统提示.

    只包含用户原始提示词与模板规则描述（不使用创作 AI 提炼的主题描述）。

    Args:
        poem: 诗行列表。
        template: 模板字典。
        user_prompt: 用户发给创作 AI 的原始提示词。
        user_feedback: 用户最近的修改反馈（若有）。

    Returns:
        系统提示文本。

    """
    parallelism_note = ""
    dim_count = 5
    if template.get("name") in ("五言律诗", "七言律诗"):
        parallelism_note = """
6. **对仗检查**: 检查颔联（第3-4行）和颈联（第5-6行）是否存在词性、结构上的对仗关系。句式结构应两两对应（如: 名词对名词、动词对动词、偏正对偏正）。若对仗明显不当或缺失，务必指出具体问题。"""
        dim_count = 6

    user_section = ""
    if user_prompt.strip():
        user_section = f"""
【用户原始要求（创作提示词）】
{user_prompt}
"""
    rule_text = _template_rule_text(template)
    rule_section = ""
    if rule_text:
        rule_section = f"""
【模板规则描述】
{rule_text}
"""
    feedback_section = ""
    if user_feedback.strip():
        feedback_section = f"""
【用户修改反馈（本轮必须落实）】
{user_feedback}
"""

    return (
        f"""你是一位严格的诗歌评审专家。请从以下{dim_count}个维度审阅诗歌，并给出结论。
{user_section}{rule_section}{feedback_section}
【诗歌文本】
"""
        + "\n".join(f"  [{i}] {line}" for i, line in enumerate(poem))
        + f"""

【评审维度】
1. **句意通顺**: 每行诗文在语义上是否通顺、自然，有无语病、逻辑断裂或意象割裂。
2. **意象与语言**: 全诗意象是否统一、用词是否恰当，有无前后矛盾、意象割裂或违和之处。
3. **用户要求符合**: 逐条核对诗歌是否符合【用户原始要求（创作提示词）】中的具体诉求（主题、意象、情感、体裁、语言、必须保留或避开的词句、翻译忠实度等），以及【模板规则描述】中的额外规则；若给出了【用户修改反馈】，检查是否已落实。与用户要求明显不符必须判为不通过，并在 suggestions 中说明哪条要求未满足。
4. **意境优美**: 全诗意境优美，不落俗套。
5. **情感真挚**: 能表达出独特真挚的情感，切不能假大空。{parallelism_note}

请确认没有遗漏用户明确提出的其它要求（如必须出现的词、不能出现的表达等）。
请调用 submit 工具给出评审结论:
- pass: true 表示所有{dim_count}个检查维度全部通过
- pass: false 表示任一维度存在问题，必须在 suggestions 中按维度逐条说明具体问题和修改建议"""
    )


class CheckerAI:
    """句意终审代理（独立 LLM 端点/模型）."""

    def __init__(self, config: dict[str, Any]):
        """初始化检查 AI.

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
        poem: list[str],
        template: dict[str, Any],
        user_prompt: str = "",
        user_feedback: str = "",
    ) -> CheckResult:
        """执行句意终审（最多重试 3 轮直到拿到 submit 结论）.

        Args:
            poem: 诗行列表。
            template: 模板字典。
            user_prompt: 用户发给创作 AI 的原始提示词（评审的唯一主题依据）。
            user_feedback: 用户最近的修改反馈。

        Returns:
            {"pass": bool, "suggestions": str}。

        """
        system_prompt = _build_checker_system(
            poem, template, user_prompt, user_feedback
        )
        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "请对以上诗歌进行评审，逐条核对是否满足用户原始要求与模板规则，"
                    "按维度逐一检查后调用 submit 工具给出结论。"
                ),
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
