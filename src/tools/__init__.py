# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Agent 工具定义（OpenAI Function Calling JSON Schema）。.

WRITER_TOOLS：编写 AI 可用的三个工具（search_words / modify / submit）；
CHECKER_TOOLS：检查 AI 的终审工具。
"""

from typing import Any

SEARCH_WORDS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_words",
        "description": "搜索候选词。按音节约束查找词汇（约束匹配词内任一音节位，结果中 matched_syllable 标注匹配位置），用向量相似度排序，返回最匹配的候选词。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "想表达的意思或上下文文本，用于语义相似度排序",
                },
                "syllable_count": {"type": "integer", "description": "音节数量约束"},
                "onset": {"type": "string", "description": "声母约束（空=不限）"},
                "nucleus": {"type": "string", "description": "韵母约束（空=不限）"},
                "coda": {"type": "string", "description": "韵尾约束（空=不限）"},
                "tone": {"type": "string", "description": "声调约束: 平/仄（空=不限）"},
                "stress": {
                    "type": "string",
                    "description": "轻重约束: heavy/light（空=不限）",
                },
                "length": {
                    "type": "string",
                    "description": "长短约束: long/short（空=不限）",
                },
                "limit": {"type": "integer", "description": "最大返回数量，默认20"},
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
            "修改诗稿。modify_type 指定修改类型（必传）："
            "line=修改某一行（需提供 line 行号与 content 新文本字符串）；"
            "title=修改标题（content 为标题字符串）；"
            "punctuation=修改标点（content 为标点字符串列表，长度须等于格律行数）。"
            "line 仅 line 类型需要，title/punctuation 会忽略它。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "modify_type": {
                    "type": "string",
                    "enum": ["line", "title", "punctuation"],
                    "description": "修改类型：line / title / punctuation",
                },
                "line": {
                    "type": "integer",
                    "description": "要修改的行号（从0开始）；仅 line 类型需要",
                },
                "content": {
                    "type": ["string", "array"],
                    "items": {"type": "string"},
                    "description": (
                        "修改后的内容：line/title 为字符串；"
                        "punctuation 为标点字符串列表"
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
            "提交诗稿。可通过 poem 整首替换诗稿、通过 punctuation 设置标点；"
            "程序会先执行全量格律校验，通过后才将定稿送交检查AI终审；"
            "不通过则返回具体错误，请继续修改后再次提交。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "诗稿标题，简短精炼，不超过10个字",
                },
                "poem": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "整首替换的诗稿（每行一句）；留空则沿用当前诗稿",
                },
                "punctuation": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标点列表，长度须等于格律行数；留空用默认",
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
        "description": "提交终审结果。pass=true表示通过，pass=false必须附带suggestions说明问题。",
        "parameters": {
            "type": "object",
            "properties": {
                "pass": {
                    "type": "boolean",
                    "description": "句意是否通顺、整体是否通过",
                },
                "suggestions": {"type": "string", "description": "不通过时的修改建议"},
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
