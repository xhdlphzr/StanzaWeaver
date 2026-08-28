# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""refine_line 工具执行单元测试（符号层，纯格律校验）。"""

from src.tools import refine_line as refine_line_module

ZH_TPL = {
    "name": "五绝",
    "language": "zh",
    "lines": 4,
    "syllables_per_line": [5, 5, 5, 5],
    "syllable_constraints": None,
}

ZH_TPL_CONSTRAINT = {
    "name": "五绝",
    "language": "zh",
    "lines": 4,
    "syllables_per_line": [5, 5, 5, 5],
    "syllable_constraints": [[{"attributes": {"tone": "平"}}]],
}

POEM = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_refine_line_valid() -> None:
    result = refine_line_module.execute_refine_line(
        list(POEM), ZH_TPL, {"line": 0, "new_text": "窗前明月光"}
    )
    assert "poem" in result
    assert result["poem"][0] == "窗前明月光"
    assert result["changed_line"] == 0


def test_refine_line_wrong_syllable_count() -> None:
    result = refine_line_module.execute_refine_line(
        list(POEM), ZH_TPL, {"line": 0, "new_text": "窗前明月"}
    )
    assert "error" in result
    assert any("音节数" in e for e in result["error"])


def test_refine_line_out_of_range() -> None:
    result = refine_line_module.execute_refine_line(
        list(POEM), ZH_TPL, {"line": 10, "new_text": "窗前明月光"}
    )
    assert "error" in result
    assert "越界" in result["error"]


def test_refine_line_constraints_mismatch() -> None:
    # 去 (仄) 不满足第 1 行第 1 音节平声约束
    result = refine_line_module.execute_refine_line(
        list(POEM), ZH_TPL_CONSTRAINT, {"line": 0, "new_text": "去前明月光"}
    )
    assert "error" in result
    assert any("第1音节" in e for e in result["error"])
