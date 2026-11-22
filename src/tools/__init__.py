# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Agent tool definitions (OpenAI Function Calling JSON Schema).

WRITER_TOOLS: the three tools available to the writer AI (search_words /
modify / submit); CHECKER_TOOLS: final-review tools for the checker AI.
"""

from typing import Any

SEARCH_WORDS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_words",
        "description": (
            "Search candidate words. Find vocabulary by syllable constraints "
            "(a constraint matches any syllable position in the word; "
            "matched_syllable marks the matched position), rank by vector "
            "similarity, and return the best candidates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Meaning or context to express, used for semantic "
                        "similarity ranking"
                    ),
                },
                "syllable_count": {
                    "type": "integer",
                    "description": "Syllable-count constraint",
                },
                "onset": {
                    "type": "string",
                    "description": "Onset constraint (empty = unconstrained)",
                },
                "nucleus": {
                    "type": "string",
                    "description": "Nucleus constraint (empty = unconstrained)",
                },
                "coda": {
                    "type": "string",
                    "description": "Coda constraint (empty = unconstrained)",
                },
                "tone": {
                    "type": "string",
                    "description": "Tone constraint: 平/仄 (empty = unconstrained)",
                },
                "stress": {
                    "type": "string",
                    "description": (
                        "Stress constraint: heavy/light (empty = unconstrained)"
                    ),
                },
                "length": {
                    "type": "string",
                    "description": (
                        "Length constraint: long/short (empty = unconstrained)"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results, default 20",
                },
            },
            "required": [],
        },
    },
}

MODIFY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "modify",
        "description": (
            "Modify the poem draft. modify_type selects the modification type "
            "(required): line=replace one line (provide the line number and a "
            "content string); title=replace the title (content is the title "
            "string); punctuation=replace punctuation (content is a list of "
            "punctuation strings whose length must equal the meter line count). "
            "line is needed only for the line type; title/punctuation ignore it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "modify_type": {
                    "type": "string",
                    "enum": ["line", "title", "punctuation"],
                    "description": "Modification type: line / title / punctuation",
                },
                "line": {
                    "type": "integer",
                    "description": (
                        "Line number to modify (0-based); needed only for the line type"
                    ),
                },
                "content": {
                    "type": ["string", "array"],
                    "items": {"type": "string"},
                    "description": (
                        "New content: a string for line/title; a list of "
                        "punctuation strings for punctuation"
                    ),
                },
            },
            "required": ["modify_type"],
        },
    },
}

SUBMIT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit",
        "description": (
            "Submit the poem draft. Use poem to replace the whole draft and "
            "punctuation to set punctuation; the program runs a full meter "
            "validation first and only sends a passing draft to the checker AI "
            "for final review; on failure it returns specific errors, so keep "
            "revising and submit again."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Poem title, short and refined, no more than 10 characters"
                    ),
                },
                "poem": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Replacement poem (one sentence per line); leave empty "
                        "to keep the current draft"
                    ),
                },
                "punctuation": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Punctuation list whose length must equal the meter line "
                        "count; leave empty for defaults"
                    ),
                },
            },
            "required": ["title"],
        },
    },
}

CHECKER_SUBMIT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit",
        "description": (
            "Submit the final review result. pass=true means passed; pass=false "
            "must include suggestions describing the problems."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pass": {
                    "type": "boolean",
                    "description": (
                        "Whether the meaning reads smoothly and the poem passes overall"
                    ),
                },
                "suggestions": {
                    "type": "string",
                    "description": "Suggested revisions when not passed",
                },
            },
            "required": ["pass"],
        },
    },
}

WRITER_TOOLS: list[dict[str, Any]] = [
    SEARCH_WORDS_TOOL,
    MODIFY_TOOL,
    SUBMIT_TOOL,
]
CHECKER_TOOLS: list[dict[str, Any]] = [CHECKER_SUBMIT_TOOL]
