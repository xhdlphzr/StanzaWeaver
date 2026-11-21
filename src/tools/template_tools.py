# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""模板编辑 AI 的工具定义与执行.

模板编辑 AI 通过这些工具配置自定义模板，与用户在界面上可配置的内容一一
对应：模板信息（名称/语言/行数）、每行音节数、约束种类数、逐位音节约束、
押韵韵式、自定义校验代码。AI 只修改内存中的草稿，最后可调用
``submit_template`` 由服务端落盘并注册模板。
"""

from dataclasses import dataclass, field
from typing import Any

from ..templates import ConstraintTable
from ..templates.convert import (
    constraint_scheme,
    constraint_tables_to_values,
    convert_template,
    normalize_constraint_value,
)

#: 约束种类数量上限。
MAX_CONSTRAINT_KINDS = 8

#: 模板行数上限。
MAX_TEMPLATE_LINES = 30

#: 允许的语言列表。
SUPPORTED_LANGUAGES: tuple[str, ...] = ("zh", "en", "it", "fr", "la")

SET_TEMPLATE_INFO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_template_info",
        "description": (
            "设置模板基本信息：名称、语言、行数。语言决定逐位约束可用的属性："
            "zh 用平/仄；en/it 用 light/heavy；la 用 long/short；fr 无逐位属性。"
            "修改行数会自动调整每行音节数与约束表。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "模板名称，如“浣溪沙”"},
                "language": {
                    "type": "string",
                    "enum": list(SUPPORTED_LANGUAGES),
                    "description": "语言代码",
                },
                "lines": {"type": "integer", "description": "行数（1-30）"},
            },
            "required": [],
        },
    },
}

SET_SYLLABLES_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_syllables_per_line",
        "description": (
            "设置每行音节数。数组长度必须等于模板行数；约束表会自动按新音节数调整。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "syllables": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "每行音节数，如 [7,7,7,7]",
                },
            },
            "required": ["syllables"],
        },
    },
}

SET_KIND_COUNT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_constraint_kind_count",
        "description": (
            "设置“约束种类”数量（1-8）。多种约束之间是“或”的关系："
            "AI 生成诗歌时只需满足任意一种即可，例如绝句的仄起/平起四种格式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "约束种类数量（1-8）"},
            },
            "required": ["count"],
        },
    },
}

SET_CONSTRAINTS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_syllable_constraints",
        "description": (
            "填写某一种约束的逐位音节约束。constraints 是二维数组：外层每行一项，"
            "内层每个音节一项，值为该语言属性的规范值或空串（空串=该位自由）。"
            "规范值：zh 用 平/仄；en、it 用 light/heavy；la 用 long/short；"
            "fr 只接受空串。也接受中文别名 重/轻/长/短。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "alternative": {
                    "type": "integer",
                    "description": "第几种约束（从 0 开始，默认 0）",
                },
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": "逐行逐音节的约束值，如 [[平,仄,平,仄,平], ...]",
                },
            },
            "required": ["constraints"],
        },
    },
}

SET_FROM_TEMPLATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_from_template",
        "description": (
            "从已有模板（任意语言）转化：行数、每行音节数、约束种类、押韵韵式与"
            "自定义代码原样复制，仅把逐位约束的源语言属性值按 mapping 映射为目标"
            "语言属性值，例如 "
            '{"平": "heavy", "仄": "light"}。允许把多个源值映射到同一个目标值'
            "（多对一），但每个源值只能有一个目标值。未列出的源值视为自由。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_key": {
                    "type": "string",
                    "description": "源模板 key，如 zh_wujue / en_sonnet",
                },
                "mapping": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "源属性值 → 目标属性值的映射",
                },
            },
            "required": ["template_key"],
        },
    },
}

SET_RHYME_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_rhyme_scheme",
        "description": (
            "设置押韵韵式，例如莎士比亚商籁体为 ABAB CDCD EFEF GG；"
            "相同字母的行必须押韵，'-' 表示该行不押韵，不能押韵的行用 '-' 占位。"
            "distinct=true 时要求不同韵组互不相同（如商籁体 A/B 韵不同）。传空串清除押韵规则。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scheme": {
                    "type": "string",
                    "description": "韵式字符串，如 ABAB CDCD EFEF GG",
                },
                "distinct": {
                    "type": "boolean",
                    "description": "不同韵组是否必须互不相同，默认 false",
                },
            },
            "required": ["scheme"],
        },
    },
}

SET_RULE_DESCRIPTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_rule_description",
        "description": (
            "设置模板规则描述。这段文字会作为 prompt 提供给生成诗歌的写作 AI，"
            "用于说明逐位约束/韵式之外的自然语言规则（体裁、句式、对仗、意象结构等）。"
            "传空串清除。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "要提供给写作 AI 的模板规则描述",
                },
            },
            "required": ["description"],
        },
    },
}

SET_CODE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_custom_code",
        "description": (
            "设置自定义整体校验代码（Python，会写入生成模板的 validate_full 中，"
            "在逐位约束与押韵检查之后执行；可用 errors.append(...) 追加错误，"
            "可经 rules.<函数名> 复用该语言的辅助函数）。传空串清除。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python 代码（不要包含 def validate_full 定义）",
                },
            },
            "required": ["code"],
        },
    },
}

GET_DRAFT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_template_draft",
        "description": "读取当前模板草稿的完整内容（名称/语言/行数/约束表/韵式/代码）。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

SUBMIT_TEMPLATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_template",
        "description": (
            "提交模板：服务端会校验并生成模板文件、注册模板。"
            "只有在模板名称、语言、行数与约束都设置完成后才调用。"
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

TEMPLATE_TOOLS: list[dict[str, Any]] = [
    SET_TEMPLATE_INFO_TOOL,
    SET_SYLLABLES_TOOL,
    SET_KIND_COUNT_TOOL,
    SET_CONSTRAINTS_TOOL,
    SET_FROM_TEMPLATE_TOOL,
    SET_RHYME_TOOL,
    SET_RULE_DESCRIPTION_TOOL,
    SET_CODE_TOOL,
    GET_DRAFT_TOOL,
    SUBMIT_TEMPLATE_TOOL,
]


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """把任意值转为区间内的整数.

    Args:
        value: 原始值。
        default: 无法转换时的默认值。
        minimum: 下限。
        maximum: 上限。

    Returns:
        区间内的整数。

    """
    try:
        number = int(value)
    except TypeError, ValueError:
        number = default
    return max(minimum, min(number, maximum))


@dataclass
class TemplateDraft:
    """模板编辑 AI 的可变草稿（在内存中逐步配置）."""

    name: str = ""
    language: str = "zh"
    lines: int = 4
    syllables_per_line: list[int] = field(default_factory=lambda: [7, 7, 7, 7])
    #: 约束种类 -> 行 -> 每音节的规范值（"" 表示自由）。
    alternatives: list[list[list[str]]] = field(
        default_factory=lambda: [[[""] * 7 for _ in range(4)]]
    )
    rhyme_scheme: str = ""
    rhyme_distinct: bool = False
    code: str = ""
    #: 已数据化的结构规则（如近体诗平仄骨架/三平尾/孤平），随转化复制。
    structural_rules: dict[str, Any] | None = None
    #: 用户填写的模板规则描述（会作为 prompt 提供给写作 AI）。
    rule_note: str = ""
    submitted: bool = False

    def normalize(self) -> None:
        """把草稿各字段规整到合法范围并补齐缺失的约束单元格."""
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "zh"
        self.lines = _clamp_int(self.lines, 4, 1, MAX_TEMPLATE_LINES)
        syllables: list[int] = []
        for item in self.syllables_per_line[: self.lines]:
            syllables.append(_clamp_int(item, 7, 1, 100))
        while len(syllables) < self.lines:
            syllables.append(syllables[-1] if syllables else 7)
        self.syllables_per_line = syllables

        from ..templates.structural import normalize_structural_rules

        rules, rules_error = normalize_structural_rules(self.structural_rules)
        self.structural_rules = None if rules_error else rules
        self.rule_note = str(self.rule_note or "")[:4000]

        if not self.alternatives:
            self.alternatives = [[[""] * count for count in syllables]]
        alternatives: list[list[list[str]]] = []
        for alternative in self.alternatives[:MAX_CONSTRAINT_KINDS]:
            table: list[list[str]] = []
            for i in range(self.lines):
                line = list(alternative[i]) if i < len(alternative) else []
                values: list[str] = []
                for j in range(syllables[i]):
                    raw = line[j] if j < len(line) else ""
                    normalized = normalize_constraint_value(self.language, raw)
                    values.append(normalized if normalized is not None else "")
                table.append(values)
            alternatives.append(table)
        self.alternatives = alternatives

    def to_payload(self) -> dict[str, Any]:
        """序列化为前端可消费的草稿字典.

        Returns:
            {name, language, lines, syllables_per_line, alternatives,
             rhyme_scheme, rhyme_distinct, code}。

        """
        return {
            "name": self.name,
            "language": self.language,
            "lines": self.lines,
            "syllables_per_line": list(self.syllables_per_line),
            "alternatives": [
                [list(line) for line in table] for table in self.alternatives
            ],
            "rhyme_scheme": self.rhyme_scheme,
            "rhyme_distinct": self.rhyme_distinct,
            "code": self.code,
            "structural_rules": (
                dict(self.structural_rules) if self.structural_rules else None
            ),
            "rule_note": self.rule_note,
        }

    def constraint_tables(self) -> list[ConstraintTable]:
        """把值表转换为模板约束字典表（供生成模板源码）.

        Returns:
            每份约束一个 ConstraintTable。

        """
        attribute, _values = constraint_scheme(self.language)
        tables: list[ConstraintTable] = []
        for alternative in self.alternatives:
            table: ConstraintTable = []
            for line in alternative:
                cells: list[dict[str, Any]] = []
                for value in line:
                    attributes = {"tone": "", "stress": "", "length": ""}
                    if attribute and value:
                        attributes[attribute] = value
                    cells.append(
                        {
                            "onset": "",
                            "nucleus": "",
                            "coda": "",
                            "attributes": attributes,
                        }
                    )
                table.append(cells)
            tables.append(table)
        return tables


def draft_from_payload(payload: dict[str, Any]) -> TemplateDraft:
    """从前端提交的草稿字典构造并规整 TemplateDraft.

    Args:
        payload: 前端草稿（字段不合法时按默认值容错）。

    Returns:
        规整后的 TemplateDraft。

    """
    draft = TemplateDraft()
    draft.name = str(payload.get("name", "")).strip()
    draft.language = str(payload.get("language", "zh"))
    draft.code = str(payload.get("code", ""))
    draft.rhyme_scheme = str(payload.get("rhyme_scheme", "")).strip()
    draft.rhyme_distinct = bool(payload.get("rhyme_distinct", False))
    try:
        draft.lines = int(payload.get("lines", 4))
    except TypeError, ValueError:
        draft.lines = 4
    raw_syllables = payload.get("syllables_per_line")
    if isinstance(raw_syllables, list) and raw_syllables:
        draft.syllables_per_line = list(raw_syllables)
    draft.rule_note = str(payload.get("rule_note", "") or "")
    raw_rules = payload.get("structural_rules")
    if isinstance(raw_rules, dict):
        draft.structural_rules = raw_rules
    raw_alternatives = payload.get("alternatives")
    alternatives: list[list[list[str]]] = []
    if isinstance(raw_alternatives, list):
        for alternative in raw_alternatives:
            if not isinstance(alternative, list):
                continue
            table: list[list[str]] = []
            for line in alternative:
                if isinstance(line, list):
                    table.append([str(cell) for cell in line])
                else:
                    table.append([])
            alternatives.append(table)
    if alternatives:
        draft.alternatives = alternatives
    draft.normalize()
    return draft


def _draft_summary(draft: TemplateDraft) -> dict[str, Any]:
    """返回草稿的简短摘要（工具结果用）.

    Args:
        draft: 模板草稿。

    Returns:
        简短摘要字典。

    """
    return {
        "name": draft.name,
        "language": draft.language,
        "lines": draft.lines,
        "syllables_per_line": list(draft.syllables_per_line),
        "constraint_kinds": len(draft.alternatives),
        "rhyme_scheme": draft.rhyme_scheme,
        "rhyme_distinct": draft.rhyme_distinct,
        "has_custom_code": bool(draft.code.strip()),
        "has_structural_rules": draft.structural_rules is not None,
        "has_rule_note": bool(draft.rule_note.strip()),
    }


def execute_set_template_info(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_template_info.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（name/language/lines）。

    Returns:
        ok 或 error 结果字典。

    """
    if "name" in arguments:
        name = str(arguments.get("name", "")).strip()
        if not name:
            return {"error": "模板名称不能为空"}
        draft.name = name
    if "language" in arguments:
        language = str(arguments.get("language", "")).strip()
        if language not in SUPPORTED_LANGUAGES:
            return {"error": f"不支持的语言 {language!r}"}
        draft.language = language
    if "lines" in arguments:
        draft.lines = _clamp_int(arguments.get("lines"), draft.lines, 1, 30)
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_syllables(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_syllables_per_line.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（syllables）。

    Returns:
        ok 或 error 结果字典。

    """
    raw = arguments.get("syllables")
    if not isinstance(raw, list):
        return {"error": "syllables 必须是整数数组"}
    if len(raw) != draft.lines:
        return {"error": f"音节数组长度应为 {draft.lines}，实际 {len(raw)}"}
    syllables: list[int] = []
    for item in raw:
        try:
            syllables.append(int(item))
        except TypeError, ValueError:
            return {"error": "syllables 必须全部是整数"}
    if any(value < 1 for value in syllables):
        return {"error": "每行音节数必须为正整数"}
    draft.syllables_per_line = syllables
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_kind_count(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_constraint_kind_count.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（count）。

    Returns:
        ok 或 error 结果字典。

    """
    try:
        count = int(arguments.get("count", 1))
    except TypeError, ValueError:
        return {"error": "count 必须是整数"}
    if count < 1 or count > MAX_CONSTRAINT_KINDS:
        return {"error": f"约束种类数量应在 1-{MAX_CONSTRAINT_KINDS} 之间"}
    draft.normalize()
    while len(draft.alternatives) < count:
        draft.alternatives.append([[""] * n for n in draft.syllables_per_line])
    draft.alternatives = draft.alternatives[:count]
    draft.normalize()
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_constraints(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_syllable_constraints.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（alternative/constraints）。

    Returns:
        ok 或 error 结果字典。

    """
    raw = arguments.get("constraints")
    if not isinstance(raw, list):
        return {"error": "constraints 必须是二维数组"}
    draft.normalize()
    try:
        alternative_index = int(arguments.get("alternative", 0))
    except TypeError, ValueError:
        return {"error": "alternative 必须是整数"}
    if alternative_index < 0 or alternative_index >= len(draft.alternatives):
        return {"error": f"alternative 越界：当前共 {len(draft.alternatives)} 种约束"}
    table: list[list[str]] = []
    for i in range(len(draft.alternatives[alternative_index])):
        row = raw[i] if i < len(raw) else []
        if not isinstance(row, list):
            row = []
        values: list[str] = []
        for j in range(draft.syllables_per_line[i]):
            cell = row[j] if j < len(row) else ""
            normalized = normalize_constraint_value(draft.language, cell)
            if normalized is None:
                return {"error": f"第{i + 1}行第{j + 1}位约束值 {cell!r} 不合法"}
            values.append(normalized)
        table.append(values)
    draft.alternatives[alternative_index] = table
    draft.normalize()
    return {
        "status": "ok",
        "alternative": alternative_index,
        "cells": sum(len(row) for row in table),
    }


def execute_set_from_template(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_from_template（统一的跨语言模板转化）.

    转化由 :func:`src.templates.convert.convert_template` 完成：行数、音节数、
    约束种类、押韵韵式与自定义代码原样复制，只有逐位约束的属性值按映射转换。

    Args:
        draft: 模板草稿（就地修改）。
        arguments: 工具参数（template_key / mapping）。

    Returns:
        ok 或 error 结果字典。

    """
    key = str(arguments.get("template_key", "")).strip()
    if not key:
        return {"error": "template_key 不能为空"}
    spec, error = convert_template(key, draft.language, arguments.get("mapping"))
    if error:
        return {"error": error}
    draft.lines = int(spec["lines"])
    draft.syllables_per_line = list(spec["syllables_per_line"])
    draft.alternatives = constraint_tables_to_values(
        list(spec["alternatives"]), draft.language
    )
    draft.rhyme_scheme = str(spec["rhyme_scheme"])
    draft.rhyme_distinct = bool(spec["rhyme_distinct"])
    draft.code = str(spec["code"])
    raw_rules = spec.get("structural_rules")
    draft.structural_rules = raw_rules if isinstance(raw_rules, dict) else None
    draft.rule_note = str(spec.get("rule_note", "") or "")
    draft.normalize()
    if not draft.name:
        draft.name = f"{spec['source_name']}-{draft.language}"
    return {
        "status": "ok",
        "template_key": key,
        "source_language": spec["source_language"],
        "mapped": spec["mapped"],
        "rhyme_scheme": draft.rhyme_scheme,
        "has_custom_code": bool(draft.code.strip()),
        "carried_rules": list(spec.get("carried_rules") or []),
        "dropped_rules": list(spec.get("dropped_rules") or []),
        **_draft_summary(draft),
    }


def execute_set_rhyme(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_rhyme_scheme.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（scheme/distinct）。

    Returns:
        ok 或 error 结果字典。

    """
    from ..templates.rhyme import normalize_rhyme_scheme

    scheme = str(arguments.get("scheme", ""))
    cleaned, error = normalize_rhyme_scheme(scheme, draft.lines)
    if error:
        return {"error": error}
    draft.rhyme_scheme = cleaned
    if "distinct" in arguments:
        draft.rhyme_distinct = bool(arguments.get("distinct"))
    return {"status": "ok", **_draft_summary(draft)}


def execute_set_rule_description(
    draft: TemplateDraft, arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行 set_rule_description（模板规则描述，作为写作 AI 的 prompt）.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（description）。

    Returns:
        ok 结果字典。

    """
    draft.rule_note = str(arguments.get("description", "") or "").strip()[:4000]
    return {"status": "ok", "has_rule_note": bool(draft.rule_note)}


def execute_set_code(draft: TemplateDraft, arguments: dict[str, Any]) -> dict[str, Any]:
    """执行 set_custom_code.

    Args:
        draft: 模板草稿。
        arguments: 工具参数（code）。

    Returns:
        ok 结果字典。

    """
    draft.code = str(arguments.get("code", "")).replace("\r\n", "\n")
    return {"status": "ok", "has_custom_code": bool(draft.code.strip())}


def execute_template_tool(
    draft: TemplateDraft, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """按工具名执行一次模板编辑操作.

    Args:
        draft: 模板草稿（就地修改）。
        name: 工具名。
        arguments: 工具参数。

    Returns:
        工具执行结果字典。

    """
    if name == "set_template_info":
        return execute_set_template_info(draft, arguments)
    if name == "set_syllables_per_line":
        return execute_set_syllables(draft, arguments)
    if name == "set_constraint_kind_count":
        return execute_set_kind_count(draft, arguments)
    if name == "set_syllable_constraints":
        return execute_set_constraints(draft, arguments)
    if name == "set_from_template":
        return execute_set_from_template(draft, arguments)
    if name == "set_rhyme_scheme":
        return execute_set_rhyme(draft, arguments)
    if name == "set_rule_description":
        return execute_set_rule_description(draft, arguments)
    if name == "set_custom_code":
        return execute_set_code(draft, arguments)
    if name == "get_template_draft":
        return {"status": "ok", "draft": draft.to_payload()}
    if name == "submit_template":
        if not draft.name:
            return {"error": "提交前请先用 set_template_info 设置模板名称"}
        draft.normalize()
        draft.submitted = True
        return {"status": "submitted", "message": "模板已提交，服务端将创建并注册"}
    return {"error": f"未知模板工具 {name}"}
