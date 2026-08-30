# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""针对 refine_line / search_words / logging_setup / config 的覆盖补全测试。

仅用于把这四个模块的 LINE 覆盖率补到 100%，不修改既有测试文件。
"""

import os
from pathlib import Path
from typing import Any

import pytest

from src import config as config_module
from src import logging_setup as logging_setup_module
from src.tools import refine_line as refine_line_module
from src.tools import search_words as search_words_module

_ZH_TPL: dict[str, Any] = {
    "name": "五绝",
    "language": "zh",
    "lines": 4,
    "syllables_per_line": [5, 5, 5, 5],
    "syllable_constraints": None,
}
_POEM: list[str] = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]


def test_execute_refine_line_non_int_line() -> None:
    """line 无法转为 int 时回退为 -1 并越界报错（覆盖 30-31）。"""
    result = refine_line_module.execute_refine_line(
        list(_POEM), _ZH_TPL, {"line": "abc", "new_text": "窗前明月光"}
    )
    assert "error" in result
    assert "越界" in result["error"]


class _FakeDB:
    """桩替换词库查询，避免触碰真实 SQLite。"""

    def __init__(self) -> None:
        """初始化桩。"""
        self.words: list[dict[str, Any]] = [{"word": "明月"}]

    def __call__(self, **kwargs: Any) -> list[dict[str, Any]]:
        """返回固定词条列表。

        Args:
            **kwargs: 透传的查询参数（此处忽略）。

        Returns:
            固定词条列表。
        """
        return self.words


def test_execute_search_words_non_int_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """limit 无法转为 int 时回退为 20（覆盖 36-37）。"""
    fake = _FakeDB()
    monkeypatch.setattr(search_words_module, "db_search", fake)
    result = search_words_module.execute_search_words(
        {"language": "zh"}, {"limit": "abc"}
    )
    assert result["words"] == fake.words


def test_get_logs_dir_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """环境变量覆盖日志目录（覆盖 39）。"""
    monkeypatch.setenv("STANZAWEAVER_LOG_DIR", str(tmp_path))
    assert logging_setup_module.get_logs_dir() == tmp_path


def test_setup_logging_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """已配置时直接返回命名 logger（覆盖 65）。"""
    monkeypatch.setattr(logging_setup_module, "_configured", True)
    logger = logging_setup_module.setup_logging()
    assert logger.name == "stanzaweaver"


def test_config_invalid_json_falls_back(tmp_path: Path) -> None:
    """配置文件存在但损坏时按空配置处理（覆盖 59-60）。"""
    path = tmp_path / "config.json"
    path.write_text("not valid json {", encoding="utf-8")
    cfg = config_module.Config(config_path=path)
    assert cfg.writer["model"] == config_module.DEFAULT_WRITER["model"]


def test_config_save_writes_file(tmp_path: Path) -> None:
    """save 写入配置文件（覆盖 65-69）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"writer": {"model": "x"}}
    cfg._loaded = True
    cfg.save()
    assert (tmp_path / "c.json").exists()


def test_config_save_chmod_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """save 时 chmod 失败被吞掉（覆盖 70-71）。"""

    def _raise_oserror(*args: Any, **kwargs: Any) -> None:
        """模拟 chmod 失败。"""
        raise OSError("denied")

    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {}
    cfg._loaded = True
    monkeypatch.setattr(os, "chmod", _raise_oserror)
    cfg.save()
    assert (tmp_path / "c.json").exists()


def test_config_writer_non_dict(tmp_path: Path) -> None:
    """writer 字段非 dict 时回退为空 dict（覆盖 83）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"writer": "bad"}
    cfg._loaded = True
    assert cfg.writer["model"] == config_module.DEFAULT_WRITER["model"]


def test_config_writer_setter(tmp_path: Path) -> None:
    """writer setter 写入数据（覆盖 97-98）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg.writer = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["writer"] == {"base_url": "u", "api_key": "k", "model": "m"}


def test_config_checker_non_dict(tmp_path: Path) -> None:
    """checker 字段非 dict 时回退为空 dict（覆盖 110）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"checker": 123}
    cfg._loaded = True
    assert cfg.checker["model"] == config_module.DEFAULT_CHECKER["model"]


def test_config_checker_setter(tmp_path: Path) -> None:
    """checker setter 写入数据（覆盖 124-125）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg.checker = {"base_url": "u", "api_key": "k", "model": "m"}
    assert cfg._data["checker"] == {"base_url": "u", "api_key": "k", "model": "m"}


def test_config_data_property(tmp_path: Path) -> None:
    """data 属性惰性加载后返回原始字典（覆盖 134-135）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"k": "v"}
    cfg._loaded = True
    assert cfg.data == {"k": "v"}


def test_config_update(tmp_path: Path) -> None:
    """update 合并配置数据（覆盖 143-144）。"""
    cfg = config_module.Config(config_path=tmp_path / "c.json")
    cfg._data = {"a": 1}
    cfg._loaded = True
    cfg.update({"b": 2})
    assert cfg._data == {"a": 1, "b": 2}


def test_reset_config(tmp_path: Path) -> None:
    """reset_config 清空全局单例（覆盖 165）。"""
    config_module.get_config()
    config_module.reset_config()
    assert config_module._config is None
