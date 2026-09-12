# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""modify 工具执行：按类型修改诗稿（行 / 标题 / 标点）。.

- line：整行替换（前置单行格律校验）；
- title：替换标题；
- punctuation：替换标点列表（长度须等于格律行数）。
"""

from typing import Any

from ..prosody.meter_validator import MeterValidator

#: 合法的修改类型。
MODIFY_TYPES: tuple[str, ...] = ("line", "title", "punctuation")


def execute_modify(
    poem: list[str],
    template: dict[str, Any],
    arguments: dict[str, Any],
    title: str = "",
    punctuation: list[str] | None = None,
) -> dict[str, Any]:
    """执行一次修改。.

    Args:
        poem: 当前诗稿（正文行）。
        template: 模板字典。
        arguments: 工具参数（modify_type / line / content）。
        title: 当前标题（title 类型回传旧值）。
        punctuation: 当前标点（punctuation 类型回传旧值）。

    Returns:
        line 类型返回 {"poem", "changed_line", "old_text", "new_text"}；
        title 类型返回 {"title", "old_title"}；
        punctuation 类型返回 {"punctuation", "old_punctuation"}；
        失败统一返回 {"error": 描述}。

    """
    modify_type = str(arguments.get("modify_type", "")).strip()
    if modify_type not in MODIFY_TYPES:
        return {
            "error": f"未知修改类型 {modify_type!r}，应为 line/title/punctuation 之一"
        }
    if modify_type == "line":
        return _modify_line(poem, template, arguments)
    if modify_type == "title":
        return _modify_title(arguments, title)
    return _modify_punctuation(template, arguments, punctuation)


def _modify_line(
    poem: list[str], template: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """整行替换：校验行号与新行格律后原位替换。.

    Args:
        poem: 当前诗稿。
        template: 模板字典。
        arguments: 工具参数（line / content）。

    Returns:
        替换结果或 {"error": 描述}。

    """
    if "line" not in arguments:
        return {"error": "line 类型需要提供行数参数 line（从0开始）"}
    try:
        line_idx = int(arguments["line"])
    except TypeError, ValueError:
        return {"error": "行数参数 line 必须是整数"}
    content = arguments.get("content", "")
    if not isinstance(content, str):
        return {"error": "line 类型的 content 必须是字符串"}
    if line_idx < 0 or line_idx >= len(poem):
        return {"error": f"行号 {line_idx} 越界，共 {len(poem)} 行"}

    result = MeterValidator().validate_line(content, line_idx, template)
    if not result.passed:
        return {"error": result.errors}

    old_text = poem[line_idx]
    new_poem = list(poem)
    new_poem[line_idx] = content
    return {
        "poem": new_poem,
        "changed_line": line_idx,
        "old_text": old_text,
        "new_text": content,
    }


def _modify_title(arguments: dict[str, Any], title: str) -> dict[str, Any]:
    """替换标题（去空白后不得为空）。.

    Args:
        arguments: 工具参数（content）。
        title: 当前标题。

    Returns:
        {"title", "old_title"} 或 {"error": 描述}。

    """
    content = arguments.get("content", "")
    if not isinstance(content, str):
        return {"error": "title 类型的 content 必须是字符串"}
    new_title = content.strip()
    if not new_title:
        return {"error": "标题不能为空"}
    return {"title": new_title, "old_title": title}


def _modify_punctuation(
    template: dict[str, Any],
    arguments: dict[str, Any],
    punctuation: list[str] | None,
) -> dict[str, Any]:
    """替换标点列表（长度须等于格律行数）。.

    Args:
        template: 模板字典（提供格律行数）。
        arguments: 工具参数（content）。
        punctuation: 当前标点。

    Returns:
        {"punctuation", "old_punctuation"} 或 {"error": 描述}。

    """
    content = arguments.get("content")
    if not isinstance(content, list) or not all(
        isinstance(item, str) for item in content
    ):
        return {"error": "punctuation 类型的 content 必须是字符串列表"}
    expected = int(template.get("lines", len(content)))
    if len(content) != expected:
        return {"error": f"标点数量应为 {expected} 个，实际 {len(content)} 个"}
    return {
        "punctuation": list(content),
        "old_punctuation": list(punctuation or []),
    }
