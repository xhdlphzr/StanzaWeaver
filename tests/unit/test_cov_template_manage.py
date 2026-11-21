# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""模板注册表排序与注销的单元测试."""

from typing import Any, ClassVar

from src.templates import (
    PoetryTemplate,
    _registry,
    list_dicts,
    register,
    set_order,
    unregister,
)


class _Tpl(PoetryTemplate):
    """最简测试模板."""

    name = "测试"
    language = "zh"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [1]


def _snapshot() -> dict[str, Any]:
    """快照注册表内容/顺序."""
    return dict(_registry)


def _restore(snapshot: dict[str, Any]) -> None:
    """恢复注册表内容/顺序."""
    _registry.clear()
    _registry.update(snapshot)


def test_set_order_reorders_and_appends() -> None:
    """按给定 key 重排；未知/重复 key 忽略，未列出的模板保持原顺序追加."""
    snapshot = _snapshot()
    try:
        _registry.clear()
        register("a", _Tpl())
        register("b", _Tpl())
        register("c", _Tpl())
        result = set_order(["c", "unknown", "a", "c"])
        assert result == ["c", "a", "b"]
        assert [item["key"] for item in list_dicts()] == ["c", "a", "b"]
    finally:
        _restore(snapshot)


def test_set_order_ignores_non_string_keys() -> None:
    """非字符串 key 被忽略."""
    snapshot = _snapshot()
    try:
        _registry.clear()
        register("a", _Tpl())
        register("b", _Tpl())
        result = set_order([1, None, "b"])  # type: ignore[list-item]
        assert result == ["b", "a"]
    finally:
        _restore(snapshot)


def test_unregister() -> None:
    """注销存在/不存在的模板."""
    snapshot = _snapshot()
    try:
        _registry.clear()
        register("a", _Tpl())
        assert unregister("a") is True
        assert unregister("a") is False
    finally:
        _restore(snapshot)


def test_list_dicts_marks_custom_deletable() -> None:
    """自定义模板标记为可删除，内置模板不可删除."""
    snapshot = _snapshot()
    try:
        _registry.clear()
        register("custom_x", _Tpl())
        register("zh_x", _Tpl())
        items = {item["key"]: item for item in list_dicts()}
        assert items["custom_x"]["deletable"] is True
        assert items["zh_x"]["deletable"] is False
    finally:
        _restore(snapshot)
