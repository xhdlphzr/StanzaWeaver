# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for template registry ordering and unregistration."""

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
    """Minimal test template."""

    name = "测试"
    language = "zh"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [1]


def _snapshot() -> dict[str, Any]:
    """Take a snapshot of the registry contents and order."""
    return dict(_registry)


def _restore(snapshot: dict[str, Any]) -> None:
    """Restore the registry contents and order from a snapshot."""
    _registry.clear()
    _registry.update(snapshot)


def test_set_order_reorders_and_appends() -> None:
    """Reorder by the given keys; unknown/duplicate keys are dropped.

    Templates not listed keep their original order and are appended at the end.
    """
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
    """Non-string keys are ignored."""
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
    """Unregister an existing and a missing template."""
    snapshot = _snapshot()
    try:
        _registry.clear()
        register("a", _Tpl())
        assert unregister("a") is True
        assert unregister("a") is False
    finally:
        _restore(snapshot)


def test_list_dicts_marks_custom_deletable() -> None:
    """Custom templates are marked deletable; built-in templates are not."""
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
