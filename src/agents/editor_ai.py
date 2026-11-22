# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Template editor AI: configure custom templates conversationally via tools.

The user describes the desired template at the bottom of the custom-template
dialog. This agent repeatedly calls tools (set template info, syllable counts,
constraint kinds, per-position constraints, rhyme scheme, custom code) and
pushes each thought, answer, and tool call to the frontend in real time through
a callback; once done, the AI can call submit_template to have the server
register it.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..tools.template_tools import (
    TEMPLATE_TOOLS,
    TemplateDraft,
    draft_from_payload,
    execute_template_tool,
)
from .base import LLMClient, Message

#: Maximum number of tool rounds for the template editor AI.
MAX_EDITOR_ROUNDS = 12

EditorEvent = dict[str, Any]
EmitCallback = Callable[[EditorEvent], None] | None


def _build_editor_system(draft: TemplateDraft) -> str:
    """Build the template editor AI system prompt.

    Args:
        draft: Current template draft.

    Returns:
        System prompt text.

    """
    draft_json = json.dumps(draft.to_payload(), ensure_ascii=False, indent=2)
    return (
        "You are a meter-template configuration assistant. The user describes "
        "the poetic meter they want in natural language, and you must configure "
        "it as a StanzaWeaver custom template by calling tools.\n\n"
        "[Tool reference]\n"
        "- set_template_info: set the name/language/line count. The language "
        "determines the per-position constraint attribute: zh uses 平/仄; "
        "en and it use light/heavy; la uses long/short; fr has no per-position "
        "attribute.\n"
        "- set_syllables_per_line: set the syllable count of each line (the "
        "length must equal the line count).\n"
        "- set_constraint_kind_count: set the number of constraint kinds; the "
        "kinds are an OR relationship, so generation only needs to satisfy any "
        "one of them (e.g. the four tone patterns of a quatrain).\n"
        "- set_syllable_constraints: fill in canonical values as "
        '"constraint kind → line → syllable"; an empty string means that '
        "position is free; the Chinese aliases 重/轻/长/短 are also accepted.\n"
        "- set_from_template: convert from an existing template language: the "
        "line count/syllables per line/constraint kinds/rhyme scheme/custom "
        "code are copied as-is; only the positional constraints are converted "
        "through mapping (source attribute value → target attribute value), "
        'e.g. {"平": "heavy"}.\n'
        "- set_rule_description: fill in the template rule description "
        "(natural-language requirements for genre/sentence pattern/"
        "antithesis/structure, etc.); this text is provided as a prompt to "
        "the writing AI that generates poems.\n"
        "- set_rhyme_scheme: set the rhyme scheme, e.g. ABAB CDCD EFEF GG; "
        "lines with the same letter rhyme, '-' means the line does not rhyme, "
        "and distinct=true means different rhyme groups must differ.\n"
        "- set_custom_code: write additional Python whole-poem validation code "
        "(optional).\n"
        "- get_template_draft: read the full current draft.\n"
        "- submit_template: submit; the server creates and registers the "
        "template.\n\n"
        "[Current draft]\n"
        f"{draft_json}\n\n"
        "Please first convert the user's description completely into tool "
        "calls; when information is incomplete, make reasonable inferences. "
        "Call submit_template once everything is configured. If the user is "
        "just chatting or asking questions, answer briefly and explain how to "
        "configure the template next."
    )


@dataclass
class EditorResult:
    """Result of one template editing session."""

    draft: TemplateDraft
    submitted: bool
    message: str


class TemplateEditorAI:
    """Template editor AI agent (dedicated LLM endpoint/model)."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the template editor AI.

        Args:
            config: {"base_url", "api_key", "model"}.

        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def edit(
        self,
        prompt: str,
        payload: dict[str, Any] | None = None,
        emit: EmitCallback = None,
        max_rounds: int = MAX_EDITOR_ROUNDS,
    ) -> EditorResult:
        """Run the template editing conversation (loop until submit or no tool call).

        Args:
            prompt: The user's natural-language description of the template.
            payload: Current template draft (frontend form state).
            emit: Event callback (thinking/message/tool/info).
            max_rounds: Maximum number of tool rounds.

        Returns:
            EditorResult(draft, submitted, message).

        """

        def push(event: EditorEvent) -> None:
            """Safely push one editing event to the frontend.

            Args:
                event: Event dictionary.

            """
            if emit:
                emit(event)

        draft = draft_from_payload(payload or {})
        messages: list[Message] = [
            {"role": "system", "content": _build_editor_system(draft)},
            {"role": "user", "content": prompt},
        ]
        last_message = ""
        for round_idx in range(1, max_rounds + 1):
            try:
                response = self.client.chat(messages, tools=TEMPLATE_TOOLS)
            except Exception as e:  # noqa: BLE001 - template AI fallback: report error
                push(
                    {
                        "type": "error",
                        "round": round_idx,
                        "content": f"Template AI call failed: {e}",
                    }
                )
                return EditorResult(draft, False, f"Template AI call failed: {e}")

            reasoning = response.get("reasoning_content")
            if reasoning:
                push(
                    {
                        "type": "thinking",
                        "round": round_idx,
                        "content": str(reasoning),
                    }
                )
            content = str(response.get("content") or "").strip()
            if content:
                last_message = content
                push({"type": "message", "round": round_idx, "content": content})

            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                if not draft.name:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Please keep calling tools to finish configuring "
                                "the template: first use set_template_info to set "
                                "the name/language/line count, then set the "
                                "constraints, etc.; when done, call "
                                "submit_template."
                            ),
                        }
                    )
                    continue
                return EditorResult(
                    draft, False, content or "Template config updated from description"
                )

            results_by_id: dict[str, dict[str, Any]] = {}
            submitted = False
            for tool_call in tool_calls:
                name = str(tool_call["name"])
                arguments = tool_call.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                result = execute_template_tool(draft, name, arguments)
                results_by_id[str(tool_call["id"])] = result
                push(
                    {
                        "type": "tool",
                        "round": round_idx,
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                if name == "submit_template" and result.get("status") == "submitted":
                    submitted = True

            if submitted:
                return EditorResult(
                    draft, True, content or "Template submitted, creating..."
                )

            messages.append(LLMClient.assistant_to_message(response))
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": str(tc["id"]),
                    "content": json.dumps(
                        results_by_id.get(
                            str(tc["id"]), {"error": "Tool was not executed"}
                        ),
                        ensure_ascii=False,
                    ),
                }
                for tc in tool_calls
            )

        push(
            {
                "type": "info",
                "content": f"Stopping after reaching the maximum rounds ({max_rounds})",
            }
        )
        return EditorResult(
            draft, False, last_message or "Reached the maximum rounds; editing stopped"
        )


# --------------------------------------------------------------------------- #
# Template code AI rewriting (optional for cross-language conversion)
# --------------------------------------------------------------------------- #

_SUBMIT_CODE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_code",
        "description": (
            "Submit the rewritten Python template validation code. The code is "
            "inserted into the generated template's validate_full (do not "
            "include def/class definitions)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Rewritten Python code (filler-style; may operate on "
                        "errors/poem/syllables)"
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Rewrite notes (which rules are kept and which are "
                        "downgraded/dropped in the target language)"
                    ),
                },
            },
            "required": ["code"],
        },
    },
}

_ATTRIBUTE_LABELS: dict[str, str] = {
    "tone": "tone (level/oblique)",
    "stress": "stress (heavy/light)",
    "length": "length (long/short)",
}

_VALUE_LABELS: dict[str, str] = {
    "平": "level tone",
    "仄": "oblique tone",
    "heavy": "stressed",
    "light": "unstressed",
    "long": "long syllable",
    "short": "short syllable",
}


def format_value_mapping(
    source_language: str, target_language: str, mapping: dict[str, str]
) -> str:
    """Format the attribute-value mapping as human-readable notes for the AI.

    Args:
        source_language: Source language code.
        target_language: Target language code.
        mapping: Mapping from source attribute values to target attribute values.

    Returns:
        Multi-line description text (attribute dimensions and per-value pairs).

    """
    from ..templates.convert import constraint_scheme

    source_attribute, _ = constraint_scheme(source_language)
    target_attribute, _ = constraint_scheme(target_language)
    lines: list[str] = []
    if source_attribute or target_attribute:
        lines.append(
            f"- Attribute dimension: "
            f"{_ATTRIBUTE_LABELS.get(source_attribute, source_attribute or 'none')}"
            f" → {_ATTRIBUTE_LABELS.get(target_attribute, target_attribute or 'none')}"
        )
    if not target_attribute:
        lines.append(
            "- The target language has no per-syllable attribute; mapping "
            "values only help understand the source rules."
        )
        return "\n".join(lines)
    if not mapping:
        lines.append(
            "- No concrete attribute-value mapping was provided; source-language "
            "attribute values stay free in the target language."
        )
        return "\n".join(lines)
    for source_value in sorted(mapping):
        target_value = mapping[source_value]
        source_label = _VALUE_LABELS.get(source_value, source_value)
        target_label = _VALUE_LABELS.get(target_value, target_value)
        lines.append(
            f"- {source_value} ({source_label}) → {target_value} ({target_label})"
        )
    return "\n".join(lines)


def _build_rewrite_system(
    source_language: str,
    target_language: str,
    mapping: dict[str, str],
    source_code: str,
    target_spec: dict[str, Any],
    rule_note: str = "",
) -> str:
    """Build the template-code rewrite system prompt.

    Args:
        source_language: Source language code.
        target_language: Target language code.
        mapping: Mapping from source attribute values to target attribute values.
        source_code: Source template code.
        target_spec: Target template spec produced by deterministic conversion.
        rule_note: Template rule description.

    Returns:
        System prompt text.

    """
    spec = {
        "lines": target_spec.get("lines"),
        "syllables_per_line": target_spec.get("syllables_per_line"),
        "alternatives": target_spec.get("alternatives"),
        "rhyme_scheme": target_spec.get("rhyme_scheme"),
        "rhyme_distinct": target_spec.get("rhyme_distinct"),
        "structural_rules": target_spec.get("structural_rules"),
    }
    note_section = (
        f"\n[Template rule description]\n{rule_note}\n" if rule_note.strip() else ""
    )
    return (
        "You are a Python engineer familiar with multilingual poetic meter. "
        "Rewrite the validation code of the source-language template below "
        f"into a version for the target language ({source_language} → "
        f"{target_language}), preserving the intent of the original rules under "
        "the target language's syllable attributes and rhyme system.\n\n"
        "[Language and attribute-value mapping]\n"
        f"{format_value_mapping(source_language, target_language, mapping)}\n"
        "Note: replace the source-language attribute keys and values in the "
        "code with the target-language attribute keys and values according to "
        'the mapping above (for example, map "平" to the target value '
        "corresponding to light/heavy); if the rhyme logic needs rewriting, "
        "use the target language's generic rhyme interface rather than the "
        "source language's rhyme-group constants or phonetic functions.\n"
        f"{note_section}"
        "[Declarative spec of the target template]\n"
        f"{json.dumps(spec, ensure_ascii=False, indent=2)}\n\n"
        "[Code runtime environment]\n"
        "The rewritten code is inserted into the generated template's "
        "validate_full and can use the following names:\n"
        "- errors: list[str], error message list (append errors);\n"
        "- poem: list[str], poem lines;\n"
        "- syllables: list[list[Syllable]], syllables of each line (with "
        "target-language attributes);\n"
        "- rules: alias of the target-language template module; call its "
        "helper functions if any;\n"
        "- self.structural_rules: data-driven structural rules of the target "
        "template (if present).\n"
        "Do not use def/class, do not read or write files or access the "
        "network; do not import source-language modules.\n\n"
        "[Source template code]\n"
        "```python\n"
        f"{source_code}\n"
        "```\n\n"
        "Call the submit_code tool to submit the rewritten filler code (code) "
        "and rewrite notes (notes)."
    )


class TemplateCodeRewriter:
    """Rewrite source template validation code into the target language.

    The rewrite is performed by the template AI.
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the code rewriter.

        Args:
            config: {"base_url", "api_key", "model"}.

        """
        self.client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model=str(config["model"]),
        )

    def rewrite(
        self,
        source_language: str,
        target_language: str,
        mapping: dict[str, str],
        source_code: str,
        target_spec: dict[str, Any],
        rule_note: str = "",
        max_rounds: int = 2,
    ) -> dict[str, Any]:
        """Rewrite source template code into the target language (tool + syntax check).

        Args:
            source_language: Source language code.
            target_language: Target language code.
            mapping: Mapping from source attribute values to target attribute values.
            source_code: Source template code.
            target_spec: Target template spec produced by deterministic conversion.
            rule_note: Template rule description.
            max_rounds: Maximum number of attempts.

        Returns:
            {"status": "ok", "code", "notes"} or {"status": "error", "message"}.
        """
        messages: list[Message] = [
            {
                "role": "system",
                "content": _build_rewrite_system(
                    source_language,
                    target_language,
                    mapping,
                    source_code,
                    target_spec,
                    rule_note,
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rewrite the source template code according to the mapping "
                    "and runtime environment requirements, and call submit_code "
                    "to submit it."
                ),
            },
        ]
        for _ in range(max_rounds):
            try:
                response = self.client.chat(messages, tools=[_SUBMIT_CODE_TOOL])
            except Exception as e:  # noqa: BLE001 - code rewrite fallback: report error
                return {
                    "status": "error",
                    "message": f"Template code AI rewrite failed: {e}",
                }
            arguments: dict[str, Any] | None = None
            for tool_call in response.get("tool_calls") or []:
                if str(tool_call.get("name")) == "submit_code":
                    raw = tool_call.get("arguments")
                    arguments = raw if isinstance(raw, dict) else {}
                    break
            if arguments is not None:
                code = str(arguments.get("code", "") or "").strip()
                notes = str(arguments.get("notes", "") or "")
                if not code:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The submitted code is empty; call submit_code again."
                            ),
                        }
                    )
                    continue
                try:
                    compile(code, "<ai-template-code>", "exec")
                except SyntaxError as e:
                    messages.append(LLMClient.assistant_to_message(response))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The code has a syntax error ({e}); fix it and "
                                "call submit_code again to submit."
                            ),
                        }
                    )
                    continue
                return {"status": "ok", "code": code, "notes": notes}
            messages.append(LLMClient.assistant_to_message(response))
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Be sure to call the submit_code tool to submit the "
                        "rewritten code."
                    ),
                }
            )
        return {
            "status": "error",
            "message": (
                "Template code AI rewrite did not produce valid code within the "
                "allowed rounds"
            ),
        }
