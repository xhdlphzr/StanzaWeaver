# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the modify tool execution (symbol layer, pure meter validation)."""

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
    """Line type: replace a valid new line in place."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": "窗前明月光"}
    )
    assert "poem" in result
    assert result["poem"][0] == "窗前明月光"
    assert result["changed_line"] == 0


def test_modify_line_wrong_syllable_count() -> None:
    """Line type: return an error when the syllable count does not match."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": "窗前明月"}
    )
    assert "error" in result
    assert any("Syllable count mismatch" in e for e in result["error"])


def test_modify_line_out_of_range() -> None:
    """Line type: return an error when the line number is out of range."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 10, "content": "窗前明月光"}
    )
    assert "error" in result
    assert "out of range" in result["error"]


def test_modify_line_constraints_mismatch() -> None:
    """Line type: return an error when a per-position constraint fails."""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL_CONSTRAINT,
        {"modify_type": "line", "line": 0, "content": "望前明月光"},
    )
    assert "error" in result
    assert any("Syllable 1" in e for e in result["error"])


def test_modify_line_missing_line_param() -> None:
    """Line type: report the missing line argument."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "content": "窗前明月光"}
    )
    assert "error" in result
    assert "line argument" in result["error"]


def test_modify_line_non_int_line() -> None:
    """Line type: return an error when line cannot be converted to int."""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL,
        {"modify_type": "line", "line": "abc", "content": "窗前明月光"},
    )
    assert "error" in result
    assert "integer" in result["error"]


def test_modify_line_content_not_str() -> None:
    """Line type: return an error when content is not a string."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "line", "line": 0, "content": ["x"]}
    )
    assert "error" in result
    assert "must be a string" in result["error"]


def test_modify_unknown_type() -> None:
    """Return an error for an unknown modify_type."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "unknown", "content": "x"}
    )
    assert "error" in result
    assert "Unknown modify type" in result["error"]


def test_modify_title_valid() -> None:
    """Title type: replace the title."""
    result = modify_module.execute_modify(
        list(POEM),
        ZH_TPL,
        {"modify_type": "title", "content": " 新标题 "},
        title="旧标题",
    )
    assert result["title"] == "新标题"
    assert result["old_title"] == "旧标题"


def test_modify_title_not_str() -> None:
    """Title type: return an error when content is not a string."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "title", "content": ["x"]}
    )
    assert "error" in result


def test_modify_title_empty() -> None:
    """Title type: return an error for an empty title."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "title", "content": "   "}
    )
    assert "error" in result
    assert "Title cannot be empty" in result["error"]


def test_modify_punctuation_valid() -> None:
    """Punctuation type: accept a valid punctuation list."""
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
    """Punctuation type: return an error when content is not a list."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": "，"}
    )
    assert "error" in result


def test_modify_punctuation_non_str_items() -> None:
    """Punctuation type: return an error when list items are not strings."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": [1, 2, 3, 4]}
    )
    assert "error" in result


def test_modify_punctuation_wrong_length() -> None:
    """Punctuation type: return an error when the count differs from the line count."""
    result = modify_module.execute_modify(
        list(POEM), ZH_TPL, {"modify_type": "punctuation", "content": ["，", "。"]}
    )
    assert "error" in result
    assert "punctuation items" in result["error"]


def test_modify_punctuation_ci_length() -> None:
    """For ci templates (7 lines), the punctuation count must equal the line count."""
    tpl: dict[str, Any] = {
        "language": "zh",
        "lines": 7,
        "syllables_per_line": [6, 6, 5, 6, 2, 2, 6],
    }
    poem = [f"句{i}" for i in range(7)]
    ok = modify_module.execute_modify(
        poem, tpl, {"modify_type": "punctuation", "content": ["，"] * 7}
    )
    assert ok["punctuation"] == ["，"] * 7
    bad = modify_module.execute_modify(
        poem, tpl, {"modify_type": "punctuation", "content": ["，"] * 6}
    )
    assert "Expected 7 punctuation items" in bad["error"]
