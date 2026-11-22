# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Test fixtures for pytest.

- Register all meter templates (used by MeterValidator / Pipeline);
- Seed CMUdict offline so the English analyzer can be tested without network;
- Provide helpers to build template dictionaries.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Mark the test environment: app's background auto-import thread skips it so
# the temporary test vocabulary is not polluted.
os.environ["STANZA_WEAVER_TEST"] = "1"

from src.knowledge import vocabulary
from src.prosody import english as english_module
from src.templates.en import register_english_templates
from src.templates.fr import register_french_templates
from src.templates.it import register_italian_templates
from src.templates.la import register_latin_templates
from src.templates.zh import register_chinese_templates


@pytest.fixture(autouse=True, scope="session")
def _register_all_templates() -> None:
    """Session-scoped fixture: register all built-in templates."""
    register_chinese_templates()
    register_english_templates()
    register_italian_templates()
    register_french_templates()
    register_latin_templates()


@pytest.fixture(autouse=True, scope="session")
def _init_session_db() -> Iterator[None]:
    """Session-scoped fixture: initialize the vocabulary DB (with en_pron)."""
    prev = vocabulary._DB_PATH
    tmp = Path(tempfile.mkdtemp(prefix="stanza_weaver_test_"))
    vocabulary.set_db_path(tmp / "test_vocab.db")
    vocabulary.init_db()
    yield
    vocabulary._DB_PATH = prev


@pytest.fixture(autouse=True, scope="session")
def _redirect_history_db() -> Iterator[None]:
    """Session-scoped fixture: redirect the history DB to a temp file."""
    import app as app_module

    prev = app_module._HISTORY_DB_PATH
    tmp = Path(tempfile.mkdtemp(prefix="stanza_weaver_history_"))
    app_module.set_history_db_path(tmp / "history.db")
    yield
    app_module._HISTORY_DB_PATH = prev


@pytest.fixture(autouse=True, scope="session")
def _seed_offline_cmudict() -> None:
    """Session-scoped fixture: seed a few CMUdict entries offline."""
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
    """Build a minimal Chinese template dict (only count constraints).

    Args:
        lines: Number of lines.
        per_line: Syllables per line.
        constraints: Per-position constraint table (none by default).

    Returns:
        A template dict matching the to_dict() structure.

    """
    return {
        "name": "测试模板",
        "language": "zh",
        "lines": lines,
        "syllables_per_line": [per_line] * lines,
        "syllable_constraints": constraints,
    }
