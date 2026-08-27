"""refine_line 工具执行：整行替换（前置单行格律校验）。"""

from typing import Any

from ..prosody.meter_validator import MeterValidator


def execute_refine_line(
    poem: list[str],
    template: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """执行单行重写。

    校验新行的音节数与逐位约束，通过后原位替换并返回新诗稿。

    Args:
        poem: 当前诗稿。
        template: 模板字典。
        arguments: 工具参数（line 行号、new_text 新文本）。

    Returns:
        {"poem": 新诗稿, ...} 或 {"error": 描述}。
    """
    try:
        line_idx = int(arguments.get("line", -1))
    except (TypeError, ValueError):
        line_idx = -1
    new_text = str(arguments.get("new_text", ""))

    if line_idx < 0 or line_idx >= len(poem):
        return {"error": f"行号 {line_idx} 越界，共 {len(poem)} 行"}

    validator = MeterValidator()
    result = validator.validate_line(new_text, line_idx, template)
    if not result.passed:
        return {"error": result.errors}

    old_text = poem[line_idx]
    poem[line_idx] = new_text
    return {
        "poem": list(poem),
        "changed_line": line_idx,
        "old_text": old_text,
        "new_text": new_text,
    }
