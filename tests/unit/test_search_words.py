# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""search_words 工具执行单元测试（符号层，桩替换词库查询）。"""

from typing import Any

import pytest

from src.tools import search_words as search_words_module


class _FakeDB:
    """词库查询桩：记录调用参数并返回固定结果。"""

    def __init__(self) -> None:
        """初始化桩。"""
        self.calls: list[dict[str, Any]] = []
        self.words = [{"word": "明月", "syllables": 2, "score": 0.9}]

    def __call__(self, **kwargs: Any) -> list[dict[str, Any]]:
        """记录查询参数并返回预置词条。

        Args:
            **kwargs: 透传的查询参数。

        Returns:
            预置词条列表。
        """
        self.calls.append(kwargs)
        return self.words


def test_execute_search_words_passes_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 execute search words passes args。"""
    fake = _FakeDB()
    monkeypatch.setattr(search_words_module, "db_search", fake)
    tpl = {"language": "zh", "name": "五绝"}
    result = search_words_module.execute_search_words(
        tpl, {"query": "月亮", "syllable_count": 2, "tone": "平", "limit": 5}
    )
    assert result == {"words": fake.words}
    assert fake.calls[0]["language"] == "zh"
    assert fake.calls[0]["query"] == "月亮"
    assert fake.calls[0]["syllable_count"] == 2
    assert fake.calls[0]["tone"] == "平"


def test_limit_clamping(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 limit clamping。"""
    fake = _FakeDB()
    monkeypatch.setattr(search_words_module, "db_search", fake)
    tpl = {"language": "zh"}
    search_words_module.execute_search_words(tpl, {"limit": 999})
    assert fake.calls[0]["limit"] == 50
    search_words_module.execute_search_words(tpl, {"limit": -5})
    assert fake.calls[-1]["limit"] == 1


def test_syllable_count_non_int_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 syllable count non int becomes none。"""
    fake = _FakeDB()
    monkeypatch.setattr(search_words_module, "db_search", fake)
    tpl = {"language": "zh"}
    search_words_module.execute_search_words(tpl, {"syllable_count": "五"})
    assert fake.calls[0]["syllable_count"] is None
