# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""测试夹具（pytest）。

- 注册全部格律模板（供 MeterValidator / Pipeline 使用）；
- 离线播种 CMUdict，使英语分析器无需联网即可测试；
- 提供模板字典构建工具。
"""

import os
from typing import Any

import pytest

# 标记测试环境：app 的后台自动导入线程据此跳过（避免污染测试用临时词库）。
os.environ["STANZA_WEAVER_TEST"] = "1"

from src.prosody import english as english_module
from src.templates.en import register_english_templates
from src.templates.fr import register_french_templates
from src.templates.it import register_italian_templates
from src.templates.la import register_latin_templates
from src.templates.zh import register_chinese_templates


@pytest.fixture(autouse=True, scope="session")
def _register_all_templates() -> None:
    """会话级：注册全部内置模板。"""
    register_chinese_templates()
    register_english_templates()
    register_italian_templates()
    register_french_templates()
    register_latin_templates()


@pytest.fixture(autouse=True, scope="session")
def _seed_offline_cmudict() -> None:
    """会话级：离线播种少量 CMUdict 词条，避免英语分析器联网下载。"""
    english_module._cmudict_loaded = True
    english_module._ARPABET_TO_PHONEMES = {
        "test": [["T", "EH1", "S", "T"]],
        "light": [["L", "AY1", "T"]],
        "night": [["N", "AY1", "T"]],
        "day": [["D", "EY1"]],
        "love": [["L", "AH1", "V"]],
        "stone": [["S", "T", "OW1", "N"]],
        "fire": [["F", "AY1", "ER0"]],
        "time": [["T", "AY1", "M"]],
        "happy": [["HH", "AE1", "P", "IY0"]],
    }


def make_zh_template(
    lines: int = 4,
    per_line: int = 5,
    constraints: list[Any] | None = None,
) -> dict[str, Any]:
    """构造一个最小中文模板字典（仅含数量约束）。

    Args:
        lines: 行数。
        per_line: 每行音节数。
        constraints: 逐位约束表（默认无）。

    Returns:
        模板字典（to_dict 同构）。
    """
    return {
        "name": "测试模板",
        "language": "zh",
        "lines": lines,
        "syllables_per_line": [per_line] * lines,
        "syllable_constraints": constraints,
    }
