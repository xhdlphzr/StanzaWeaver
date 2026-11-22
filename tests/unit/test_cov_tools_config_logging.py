# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Coverage completion tests for search_words / logging_setup / config.

Only used to raise the LINE coverage of these modules to 100% without modifying
existing test files.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from src import config as config_module
from src import logging_setup as logging_setup_module
from src.tools import search_words as search_words_module


class _FakeDB:
    """Fake the vocabulary lookup to avoid touching the real SQLite database."""

    def __init__(self) -> None:
        """Initialize the stub."""
        self.words: list[dict[str, Any]] = [{"word": "明月"}]

    def __call__(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return the fixed entry list.

        Args:
            **kwargs: Query arguments passed through (ignored here).

        Returns:
            The preset entry list.

        """
        return self.words


def test_execute_search_words_non_int_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Limit falls back to 20 when it cannot be converted to int (lines 36-37)."""
    fake = _FakeDB()
    monkeypatch.setattr(search_words_module, "db_search", fake)
    result = search_words_module.execute_search_words(
        {"language": "zh"}, {"limit": "abc"}
    )
    assert result["words"] == fake.words


def test_get_logs_dir_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An environment variable overrides the log directory (line 39)."""
    monkeypatch.setenv("STANZAWEAVER_LOG_DIR", str(tmp_path))
    assert logging_setup_module.get_logs_dir() == tmp_path


def test_setup_logging_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return the named logger directly when already configured (line 65)."""
    monkeypatch.setattr(logging_setup_module, "_configured", True)
    logger = logging_setup_module.setup_logging()
    assert logger.name == "stanzaweaver"


def test_config_invalid_json_falls_back(tmp_path: Path) -> None:
    """Treat a corrupt config file as empty config (lines 59-60)."""
    path = tmp_path / "config.json"
    path.write_text("not valid json {", encoding="utf-8")
    cfg = config_module.Config(config_path=path)
    assert cfg.writer["model"] == config_module.DEFAULT_WRITER["model"]


def test_config_save_writes_file(tmp_path: Path) -> None:
    """Save writes the config file with the correct content (lines 65-69)."""
    import json as _json

    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"writer": {"model": "x"}}
    cfg._loaded = True
    cfg.save()
    p = tmp_path / "c.json"
    assert p.exists()
    saved = _json.loads(p.read_text(encoding="utf-8"))
    assert saved == {"writer": {"model": "x"}}


def test_config_save_chmod_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A chmod failure during save is swallowed (lines 70-71)."""

    def _raise_oserror(*args: Any, **kwargs: Any) -> None:
        """Simulate a chmod failure.

        Args:
            *args: Passed-through arguments (ignored).
            **kwargs: Passed-through arguments (ignored).

        Raises:
            OSError: Always raised.

        """
        raise OSError("denied")

    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {}
    cfg._loaded = True
    monkeypatch.setattr(os, "chmod", _raise_oserror)
    cfg.save()
    assert (tmp_path / "c.json").exists()


def test_config_writer_non_dict(tmp_path: Path) -> None:
    """A non-dict writer field falls back to an empty dict (line 83)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"writer": "bad"}
    cfg._loaded = True
    assert cfg.writer["model"] == config_module.DEFAULT_WRITER["model"]


def test_config_writer_setter(tmp_path: Path) -> None:
    """The writer setter stores the data (lines 97-98)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg.writer = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["writer"] == {"base_url": "u", "api_key": "k", "model": "m"}


def test_config_checker_non_dict(tmp_path: Path) -> None:
    """A non-dict checker field falls back to an empty dict (line 110)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"checker": 123}
    cfg._loaded = True
    assert cfg.checker["model"] == config_module.DEFAULT_CHECKER["model"]


def test_config_checker_setter(tmp_path: Path) -> None:
    """The checker setter stores the data (lines 124-125)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg.checker = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["checker"] == {"base_url": "u", "api_key": "k", "model": "m"}


def test_config_data_property(tmp_path: Path) -> None:
    """The data property returns the raw dict after lazy loading (lines 134-135)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"k": "v"}
    cfg._loaded = True
    assert cfg.data == {"k": "v"}


def test_config_update(tmp_path: Path) -> None:
    """Update merges config data (lines 143-144)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"a": 1}
    cfg._loaded = True
    cfg.update({"b": 2})
    assert cfg._data == {"a": 1, "b": 2}


def test_config_language_default(tmp_path: Path) -> None:
    """The language property defaults to en."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    assert cfg.language == "en"


def test_config_language_zh(tmp_path: Path) -> None:
    """The language property returns zh."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"language": "zh"}
    cfg._loaded = True
    assert cfg.language == "zh"


def test_config_language_en(tmp_path: Path) -> None:
    """The language property returns en."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"language": "en"}
    cfg._loaded = True
    assert cfg.language == "en"


def test_config_language_invalid_fallback(tmp_path: Path) -> None:
    """An invalid language value falls back to en (line 137)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"language": "fr"}
    cfg._loaded = True
    assert cfg.language == "en"


def test_config_language_setter(tmp_path: Path) -> None:
    """The language setter stores the data (lines 147-148)."""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg.language = "en"
    assert cfg._data["language"] == "en"


def test_reset_config(tmp_path: Path) -> None:
    """reset_config clears the global singleton (line 165)."""
    config_module.get_config()
    config_module.reset_config()
    assert config_module._config is None
