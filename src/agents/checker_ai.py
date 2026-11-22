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
6. **Antithesis check**: Check whether the jaw couplet (lines 3-4) and the neck
couplet (lines 5-6) are antithetical in part of speech and structure. Sentence
structures should correspond pairwise (e.g. noun to noun, verb to verb,
modifier-head to modifier-head). If the antithesis is clearly improper or
missing, be sure to point out the specific problem."""
        dim_count = 6

    user_section = ""
    if user_prompt.strip():
        user_section = f"""
[User's original request (writing prompt)]
{user_prompt}
"""
    rule_text = _template_rule_text(template)
    rule_section = ""
    if rule_text:
        rule_section = f"""
[Template rule description]
{rule_text}
"""
    feedback_section = ""
    if user_feedback.strip():
        feedback_section = f"""
[User revision feedback (must be applied this round)]
{user_feedback}
"""

    return (
        f"""You are a strict poetry review expert. Review the poem across the
following {dim_count} dimensions and give a verdict.
{user_section}{rule_section}{feedback_section}
[Poem text]
"""
        + "\n".join(f"  [{i}] {line}" for i, line in enumerate(poem))
        + f"""

[Review dimensions]
1. **Meaning fluency**: Each line should read smoothly and naturally in
meaning, with no grammatical errors, logical breaks, or disjointed imagery.
2. **Imagery and language**: The imagery should be consistent throughout and
the wording appropriate, with no contradictions, disjointed imagery, or
incongruities.
3. **Compliance with user requirements**: Check item by item whether the poem
meets the specific demands in [User's original request (writing prompt)]
(theme, imagery, emotion, genre, language, words or expressions that must be
kept or avoided, translation fidelity, etc.) as well as the additional rules in
[Template rule description]; if [User revision feedback] is provided, check
whether it has been applied. A clear mismatch with the user's requirements must
be judged as not passed, and suggestions must state which requirement was not
met.
4. **Aesthetic imagery**: The whole poem should have beautiful, refined imagery
and avoid clichés.
5. **Sincere emotion**: It should express unique and sincere emotion and must
not be hollow or pretentious.{parallelism_note}

Also confirm that no other requirements explicitly stated by the user have been
missed (such as words that must appear or expressions that must not appear).
Call the submit tool to give the review verdict:
- pass: true means all {dim_count} review dimensions pass
- pass: false means at least one dimension has a problem; you must describe the
specific problems and revision suggestions dimension by dimension in
suggestions"""
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
                    "Review the poem above; check item by item whether it meets "
                    "the user's original requirements and the template rules, "
                    "examine each dimension, and then call the submit tool to "
                    "give the verdict."
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
                        "content": (
                            "Be sure to call the submit tool to give the review "
                            "verdict (pass and suggestions)."
                        ),
                    }
                )
        except Exception as e:  # noqa: BLE001 - checker fallback: failure -> fail
            return {"pass": False, "suggestions": f"Checker AI call failed: {e}"}

        return {
            "pass": False,
            "suggestions": "Checker AI did not return a verdict after several attempts",
        }
