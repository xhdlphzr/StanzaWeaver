# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Application configuration (multi-endpoint LLM).

The config file lives at ~/.stanza_weaver/config.json (mode 0600).
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

DEFAULT_EDITOR: dict[str, Any] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o",
}

LLMEndpoint = dict[str, str]


def _default_config_path() -> Path:
    """Return the default config file path.

    Returns:
        ~/.stanza_weaver/config.json.

    """
    return Path.home() / ".stanza_weaver" / "config.json"


class Config:
    """Read and write the JSON config file (lazy loading + 0600 permissions)."""

    def __init__(self, config_path: Path | None = None):
        """Initialize the config object.

        Args:
            config_path: Config file path (defaults to the default path).

        """
        self._path = config_path or _default_config_path()
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load the config file (treat a corrupt file as an empty config)."""
        if self._loaded:
            return
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except json.JSONDecodeError, OSError:
                self._data = {}
        self._loaded = True

    def save(self) -> None:
        """Write the config file back (mode 0600)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    @property
    def writer(self) -> LLMEndpoint:
        """Return the writer AI endpoint config (falls back to defaults).

        Returns:
            {"base_url", "api_key", "model"}.

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
        """Set the writer AI endpoint config.

        Args:
            value: Config dictionary.

        """
        self._ensure_loaded()
        self._data["writer"] = value

    @property
    def checker(self) -> LLMEndpoint:
        """Return the checker AI endpoint config (falls back to defaults).

        Returns:
            {"base_url", "api_key", "model"}.

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
        """Set the checker AI endpoint config.

        Args:
            value: Config dictionary.

        """
        self._ensure_loaded()
        self._data["checker"] = value

    @property
    def editor(self) -> LLMEndpoint:
        """Return the template editor AI endpoint config (falls back to defaults).

        Returns:
            {"base_url", "api_key", "model"}.

        """
        self._ensure_loaded()
        e = self._data.get("editor", {})
        if not isinstance(e, dict):
            e = {}
        return {
            "base_url": str(e.get("base_url", DEFAULT_EDITOR["base_url"])),
            "api_key": str(e.get("api_key", DEFAULT_EDITOR["api_key"])),
            "model": str(e.get("model", DEFAULT_EDITOR["model"])),
        }

    @editor.setter
    def editor(self, value: dict[str, Any]) -> None:
        """Set the template editor AI endpoint config.

        Args:
            value: Config dictionary.

        """
        self._ensure_loaded()
        self._data["editor"] = value

    @property
    def language(self) -> str:
        """Return the UI language ("zh" or "en", defaults to "en").

        Returns:
            Language code.

        """
        self._ensure_loaded()
        lang: str = str(self._data.get("language", "en"))
        if lang not in ("zh", "en"):
            lang = "en"
        return lang

    @language.setter
    def language(self, value: str) -> None:
        """Set the UI language.

        Args:
            value: Language code ("zh" or "en").

        """
        self._ensure_loaded()
        self._data["language"] = value

    @property
    def data(self) -> dict[str, Any]:
        """Return the raw config data.

        Returns:
            Config dictionary (lazily loaded).

        """
        self._ensure_loaded()
        return self._data

    def update(self, d: dict[str, Any]) -> None:
        """Merge updates into the config.

        Args:
            d: Config dictionary to merge.

        """
        self._ensure_loaded()
        self._data.update(d)


_config: Config | None = None


def get_config() -> Config:
    """Return the global config singleton.

    Returns:
        A Config instance.

    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Reset the config singleton (for tests)."""
    global _config
    _config = None
