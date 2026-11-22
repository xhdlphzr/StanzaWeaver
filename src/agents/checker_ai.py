# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Checker AI: final sentence-level review.

The checker AI reviews only on the basis of **the original prompt the user sent
to the writer AI** and **the template rule description**; it does not use the
topic description distilled by the writer AI, so the review baseline is not
skewed by the model's second-hand summary. The user's latest revision feedback
(if any) is provided as well to verify whether it was applied.

The verdict is returned through the submit tool as pass/suggestions.
"""

import json
from typing import Any

from ..tools import CHECKER_TOOLS
from .base import LLMClient, Message

CheckResult = dict[str, Any]


def _template_rule_text(template: dict[str, Any]) -> str:
    """Return the template's rule description (prefer rule_note).

    Args:
        template: Template dictionary.

    Returns:
        Rule description text; empty string when absent.

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
    """Build the checker AI system prompt.

    Contains only the user's original prompt and the template rule description
    (not the topic description distilled by the writer AI).

    Args:
        poem: List of poem lines.
        template: Template dictionary.
        user_prompt: The original prompt the user sent to the writer AI.
        user_feedback: The user's latest revision feedback (if any).

    Returns:
        System prompt text.

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
    """Final sentence-level checker (dedicated LLM endpoint/model)."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the checker AI.

        Args:
            config: {"base_url", "api_key", "model"}.

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
        """Run the final sentence-level check (retry up to 3 times until submit).

        Args:
            poem: List of poem lines.
            template: Template dictionary.
            user_prompt: Original prompt sent to the writer AI (the sole topic
                basis for the review).
            user_feedback: The user's latest revision feedback.

        Returns:
            {"pass": bool, "suggestions": str}.

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
                                    "error": (
                                        "Call the submit tool to give the review "
                                        "verdict (pass and suggestions)."
                                    )
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
        except Exception as e:  # noqa: BLE001 - checker fallback: failure -> fail
            return {"pass": False, "suggestions": f"Checker AI call failed: {e}"}

        return {
            "pass": False,
            "suggestions": "Checker AI did not return a verdict after several attempts",
        }
