# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
import os
from pathlib import Path
from typing import Optional


DEFAULT_WRITER = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o",
}

DEFAULT_CHECKER = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
}


def _default_config_path() -> Path:
    return Path.home() / ".stanza_weaver" / "config.json"


class Config:
    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or _default_config_path()
        self._data: dict = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        self._loaded = True

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    @property
    def writer(self) -> dict:
        self._ensure_loaded()
        w = self._data.get("writer", {})
        return {
            "base_url": w.get("base_url", DEFAULT_WRITER["base_url"]),
            "api_key": w.get("api_key", DEFAULT_WRITER["api_key"]),
            "model": w.get("model", DEFAULT_WRITER["model"]),
        }

    @writer.setter
    def writer(self, value: dict):
        self._ensure_loaded()
        self._data["writer"] = value

    @property
    def checker(self) -> dict:
        self._ensure_loaded()
        c = self._data.get("checker", {})
        return {
            "base_url": c.get("base_url", DEFAULT_CHECKER["base_url"]),
            "api_key": c.get("api_key", DEFAULT_CHECKER["api_key"]),
            "model": c.get("model", DEFAULT_CHECKER["model"]),
        }

    @checker.setter
    def checker(self, value: dict):
        self._ensure_loaded()
        self._data["checker"] = value

    @property
    def data(self) -> dict:
        self._ensure_loaded()
        return self._data

    def update(self, d: dict):
        self._ensure_loaded()
        self._data.update(d)


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config():
    global _config
    _config = None
