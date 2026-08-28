# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""应用配置（LLM 多端点）。

配置文件位于 ~/.stanza_weaver/config.json（权限 0600）。
"""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_WRITER: dict[str, Any] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o",
}

DEFAULT_CHECKER: dict[str, Any] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
}

LLMEndpoint = dict[str, str]


def _default_config_path() -> Path:
    """默认配置文件路径。

    Returns:
        ~/.stanza_weaver/config.json。
    """
    return Path.home() / ".stanza_weaver" / "config.json"


class Config:
    """JSON 配置文件读写（惰性加载 + 0600 权限）。"""

    def __init__(self, config_path: Path | None = None):
        """初始化配置对象。

        Args:
            config_path: 配置文件路径（缺省用默认路径）。
        """
        self._path = config_path or _default_config_path()
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """惰性加载配置文件（损坏时按空配置处理）。"""
        if self._loaded:
            return
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        self._loaded = True

    def save(self) -> None:
        """写回配置文件（0600 权限）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    @property
    def writer(self) -> LLMEndpoint:
        """编写 AI 端点配置（缺省回退默认值）。

        Returns:
            {"base_url", "api_key", "model"}。
        """
        self._ensure_loaded()
        w = self._data.get("writer", {})
        if not isinstance(w, dict):
            w = {}
        return {
            "base_url": str(w.get("base_url", DEFAULT_WRITER["base_url"])),
            "api_key": str(w.get("api_key", DEFAULT_WRITER["api_key"])),
            "model": str(w.get("model", DEFAULT_WRITER["model"])),
        }

    @writer.setter
    def writer(self, value: dict[str, Any]) -> None:
        """设置编写 AI 端点配置。

        Args:
            value: 配置字典。
        """
        self._ensure_loaded()
        self._data["writer"] = value

    @property
    def checker(self) -> LLMEndpoint:
        """检查 AI 端点配置（缺省回退默认值）。

        Returns:
            {"base_url", "api_key", "model"}。
        """
        self._ensure_loaded()
        c = self._data.get("checker", {})
        if not isinstance(c, dict):
            c = {}
        return {
            "base_url": str(c.get("base_url", DEFAULT_CHECKER["base_url"])),
            "api_key": str(c.get("api_key", DEFAULT_CHECKER["api_key"])),
            "model": str(c.get("model", DEFAULT_CHECKER["model"])),
        }

    @checker.setter
    def checker(self, value: dict[str, Any]) -> None:
        """设置检查 AI 端点配置。

        Args:
            value: 配置字典。
        """
        self._ensure_loaded()
        self._data["checker"] = value

    @property
    def data(self) -> dict[str, Any]:
        """原始配置数据。

        Returns:
            配置字典（惰性加载）。
        """
        self._ensure_loaded()
        return self._data

    def update(self, d: dict[str, Any]) -> None:
        """合并更新配置。

        Args:
            d: 要合并的配置字典。
        """
        self._ensure_loaded()
        self._data.update(d)


_config: Config | None = None


def get_config() -> Config:
    """获取全局配置单例。

    Returns:
        Config 实例。
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """重置配置单例（测试用）。"""
    global _config
    _config = None
