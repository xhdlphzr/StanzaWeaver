# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""modify 工具执行单元测试（符号层，纯格律校验）。"""

from typing import Any

from src.tools import modify as modify_module

ZH_TPL: dict[str, Any] = {
    "name": "五绝",
    "language": "zh",
    "lines": 4,
    "syllables_per_line": [5, 5, 5, 5],
    "syllable_constraints": None,
}

ZH_TPL_CONSTRAINT: dict[str, Any] = {
    "name": "五绝",
    "language": "zh",
    "lines": 4,
    "syllables_per_line": [5, 5, 5, 5],
    "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
}

POEM = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_modify_line_valid() -> None:
    """line 类型：合法新行原位替换。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": "窗前明月光"}
    )
    assert "poem" in result
    assert result["poem"][0] == "窗前明月光"
    assert result["changed_line"] == 0


def test_modify_line_wrong_syllable_count() -> None:
    """line 类型：音节数不符返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": "窗前明月"}
    )
    assert "error" in result
    assert any("音节数" in e for e in result["error"])


def test_modify_line_out_of_range() -> None:
    """line 类型：行号越界返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 10, "content": "窗前明月光"}
    )
    assert "error" in result
    assert "越界" in result["error"]


def test_modify_line_constraints_mismatch() -> None:
    """line 类型：逐位约束不符返回错误。"""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL_CONSTRAINT,
        {"modify_type": "line", "line": 0, "content": "去前明月光"},
    )
    assert "error" in result
    assert any("第1音节" in e for e in result["error"])


def test_modify_line_missing_line_param() -> None:
    """line 类型：缺少 line 参数时提示需提供行数。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "content": "窗前明月光"}
    )
    assert "error" in result
    assert "行数" in result["error"]


def test_modify_line_non_int_line() -> None:
    """line 类型：line 无法转 int 时返回错误。"""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL,
        {"modify_type": "line", "line": "abc", "content": "窗前明月光"},
    )
    assert "error" in result
    assert "整数" in result["error"]


def test_modify_line_content_not_str() -> None:
    """line 类型：content 非字符串时返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": ["x"]}
    )
    assert "error" in result
    assert "字符串" in result["error"]


def test_modify_unknown_type() -> None:
    """未知 modify_type 返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "unknown", "content": "x"}
    )
    assert "error" in result
    assert "未知修改类型" in result["error"]


def test_modify_title_valid() -> None:
    """title 类型：替换标题。"""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL,
        {"modify_type": "title", "content": " 新标题 "},
        title="旧标题",
    )
    assert result["title"] == "新标题"
    assert result["old_title"] == "旧标题"


def test_modify_title_not_str() -> None:
    """title 类型：content 非字符串返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "title", "content": ["x"]}
    )
    assert "error" in result


def test_modify_title_empty() -> None:
    """title 类型：空标题返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "title", "content": "   "}
    )
    assert "error" in result
    assert "标题不能为空" in result["error"]


def test_modify_punctuation_valid() -> None:
    """punctuation 类型：合法标点列表。"""
    marks = ["，", "。", "，", "。"]
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL,
        {"modify_type": "punctuation", "content": marks},
        punctuation=["。", "。", "。", "。"],
    )
    assert result["punctuation"] == marks
    assert result["old_punctuation"] == ["。", "。", "。", "。"]


def test_modify_punctuation_not_list() -> None:
    """punctuation 类型：content 非列表返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": "，"}
    )
    assert "error" in result


def test_modify_punctuation_non_str_items() -> None:
    """punctuation 类型：列表元素非字符串返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": [1, 2, 3, 4]}
    )
    assert "error" in result


def test_modify_punctuation_wrong_length() -> None:
    """punctuation 类型：数量与格律行数不符返回错误。"""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": ["，", "。"]}
    )
    assert "error" in result
    assert "标点数量" in result["error"]
