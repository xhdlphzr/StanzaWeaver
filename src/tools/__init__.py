# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

SEARCH_WORDS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_words",
        "description": "搜索候选词。按意思、音节约束、词性查找可用词汇，返回符合条件的所有候选词及其音节信息和释义。",
        "parameters": {
            "type": "object",
            "properties": {
                "meaning": {
                    "type": "string",
                    "description": "语义关键词，用于模糊匹配词义或文本",
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

REFINE_LINE_TOOL = {
    "type": "function",
    "function": {
        "name": "refine_line",
        "description": "重写指定某一行（整句替换）。给定行号和新的完整文本，程序会自动校验该句的音节数和逐位约束，不通过则拒绝修改并返回具体错误。",
        "parameters": {
            "type": "object",
            "properties": {
                "line": {"type": "integer", "description": "要修改的行号（从0开始）"},
                "new_text": {"type": "string", "description": "该行的新完整文本"},
            },
            "required": ["line", "new_text"],
        },
    },
}

REWRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "rewrite",
        "description": "根据指令整体重写全诗。程序会自动校验整首诗的格律约束。",
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "重写方向指令，描述希望如何调整（如'更婉约'、'换用秋景意象'等）",
                }
            },
            "required": ["instruction"],
        },
    },
}

SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit",
        "description": "提交当前诗稿。编写AI调用此工具将定稿送交检查AI终审。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

CHECKER_SUBMIT_TOOL = {
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

WRITER_TOOLS = [SEARCH_WORDS_TOOL, REFINE_LINE_TOOL, REWRITE_TOOL, SUBMIT_TOOL]
CHECKER_TOOLS = [CHECKER_SUBMIT_TOOL]
