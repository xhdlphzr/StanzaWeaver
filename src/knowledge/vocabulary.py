# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Vocabulary store access layer (SQLite).

- Word table ``words``: text, language, meaning, syllable JSON, syllable count.
- ``search_words``: query by language/syllable count/positional constraints,
  with optional vector-similarity reranking.
- The database defaults to ``~/.stanza_weaver/vocabulary.db``.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models.syllable import Syllable
from ..models.word import Word

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_DB_PATH: Path | None = None


def set_db_path(path: Path) -> None:
    """Override the database path (mainly for tests).

    Args:
        path: New database file path.

    """
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> Path:
    """Return the database path (default ``~/.stanza_weaver/vocabulary.db``).

    Returns:
        Database file path.

    """
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path.home() / ".stanza_weaver" / "vocabulary.db"
    return _DB_PATH


def init_db() -> None:
    """Initialize the database (create tables and indexes; idempotent)."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.close()


def _get_conn() -> sqlite3.Connection:
    """Open a database connection.

    Returns:
        SQLite connection.

    """
    return sqlite3.connect(str(get_db_path()))


def insert_word(word: Word) -> None:
    """Insert a single word entry (convenience wrapper, mainly for tests).

    Args:
        word: Word entry.

    """
    insert_words([word])


def insert_words(words: list[Word]) -> None:
    """Insert word entries in batches.

    Args:
        words: List of word entries.

    """
    conn = _get_conn()
    rows: list[tuple[str, str, str, str, int]] = []
    for word in words:
        syls = word.syllables
        sc = len(syls) if syls else 1
        syls_data = (
            json.dumps([s.to_dict() for s in syls], ensure_ascii=False)
            if syls
            else "[]"
        )
        rows.append((word.text, word.language, word.meaning, syls_data, sc))
    conn.executemany(
        "INSERT INTO words (text, language, meaning, syllables_json, syllable_count) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def _syl_from_json(d: dict[str, Any]) -> Syllable:
    """Restore a syllable from a dictionary.

    Args:
        d: Syllable dictionary.

    Returns:
        Syllable instance.

    """
    return Syllable.from_dict(d)


def _syl_matches(
    syl: Syllable,
    onset: str = "",
    nucleus: str = "",
    coda: str = "",
    tone: str = "",
    stress: str = "",
    length: str = "",
) -> bool:
    """Check whether a syllable satisfies the constraints (empty = unconstrained).

    Args:
        syl: Syllable.
        onset: Onset constraint (empty = unconstrained).
        nucleus: Nucleus constraint (empty = unconstrained).
        coda: Coda constraint (empty = unconstrained).
        tone: Tone constraint (empty = unconstrained).
        stress: Stress constraint (empty = unconstrained).
        length: Length constraint (empty = unconstrained).

    Returns:
        True if satisfied.

    """
    if onset and syl.onset != onset:
        return False
    if nucleus and syl.nucleus != nucleus:
        return False
    if coda and syl.coda != coda:
        return False
    if tone and syl.attributes.get("tone", "") != tone:
        return False
    if stress and syl.attributes.get("stress", "") != stress:
        return False
    return not (length and syl.attributes.get("length", "") != length)


def search_words(
    language: str,
    query: str = "",
    syllable_count: int | None = None,
    onset: str = "",
    nucleus: str = "",
    coda: str = "",
    tone: str = "",
    stress: str = "",
    length: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search candidate words by constraints.

    A constraint matches any syllable position in a word (the result marks
    ``matched_syllable``); when ``query`` is given, results are reranked by
    vector similarity.

    Args:
        language: Language code.
        query: Semantic query text (used for reranking; may be empty).
        syllable_count: Syllable-count constraint.
        onset: Onset constraint (empty = unconstrained).
        nucleus: Nucleus constraint (empty = unconstrained).
        coda: Coda constraint (empty = unconstrained).
        tone: Tone constraint (empty = unconstrained).
        stress: Stress constraint (empty = unconstrained).
        length: Length constraint (empty = unconstrained).
        limit: Maximum number of results.

    Returns:
        List of word dictionaries.

    """
    conn = _get_conn()
    conditions: list[str] = ["language = ?"]
    params: list[Any] = [language]

    if syllable_count is not None:
        conditions.append("syllable_count = ?")
        params.append(syllable_count)

    if onset or nucleus or coda or tone or stress or length:
        exist_conds: list[str] = []
        if onset:
            exist_conds.append("json_extract(j.value, '$.onset') = ?")
            params.append(onset)
        if nucleus:
            exist_conds.append("json_extract(j.value, '$.nucleus') = ?")
            params.append(nucleus)
        if coda:
            exist_conds.append("json_extract(j.value, '$.coda') = ?")
            params.append(coda)
        if tone:
            exist_conds.append("json_extract(j.value, '$.attributes.tone') = ?")
            params.append(tone)
        if stress:
            exist_conds.append("json_extract(j.value, '$.attributes.stress') = ?")
            params.append(stress)
        if length:
            exist_conds.append("json_extract(j.value, '$.attributes.length') = ?")
            params.append(length)
        exist_clause = " AND ".join(exist_conds)
        conditions.append(
            "EXISTS (SELECT 1 FROM json_each(words.syllables_json) j "
            f"WHERE {exist_clause})"
        )

    where_clause = " AND ".join(conditions)
    sql = (
        "SELECT text, language, meaning, syllables_json, syllable_count "
        f"FROM words WHERE {where_clause} ORDER BY rowid LIMIT ?"
    )
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        text, lang, meaning, syls_json, sc = row
        syllables = (
            [_syl_from_json(s) for s in json.loads(syls_json)] if syls_json else []
        )
        if not syllables:
            syllables = [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
                for _ in range(int(sc))
            ]

        match_idx: int | None = None
        if onset or nucleus or coda or tone or stress or length:
            for idx, s in enumerate(syllables):
                if _syl_matches(s, onset, nucleus, coda, tone, stress, length):
                    match_idx = idx
                    break
        results.append(
            {
                "text": text,
                "language": lang,
                "meaning": meaning,
                "syllables": [s.to_dict() for s in syllables],
                "matched_syllable": match_idx,
            }
        )
        if len(results) >= limit:
            break

    if query and results:
        from .embeddings import rerank

        results = rerank(query, results, top_k=limit)
    return results[:limit]


def word_count(language: str = "") -> int:
    """Count word entries (mainly for ``has_words`` and tests).

    Args:
        language: Language code (empty = all).

    Returns:
        Number of word entries.

    """
    conn = _get_conn()
    if language:
        count = conn.execute(
            "SELECT COUNT(*) FROM words WHERE language = ?", (language,)
        ).fetchone()[0]
    else:
        count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    conn.close()
    return int(count)


def has_words(language: str = "") -> bool:
    """Check whether the vocabulary is non-empty (mainly for tests).

    Args:
        language: Language code (empty = all).

    Returns:
        True if non-empty.

    """
    return word_count(language) > 0


def set_en_pron(word: str, prons: list[list[str]]) -> None:
    """Store all CMUdict pronunciations of an English word (local cache).

    The cache lets EnglishAnalyzer work offline.

    Args:
        word: Lowercase English word.
        prons: List of phoneme lists (each element is one pronunciation).

    """
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO en_pron (word, phones_json) VALUES (?, ?)",
        (word, json.dumps(prons, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_en_pron(word: str) -> list[list[str]] | None:
    """Read all cached CMUdict pronunciations of an English word.

    Args:
        word: Lowercase English word.

    Returns:
        List of phoneme lists; None if the word is not in the local cache or
        the table has not been created yet (callers should fall back to
        CMUdict).

    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT phones_json FROM en_pron WHERE word = ?", (word,)
        ).fetchone()
        conn.close()
    except Exception:  # noqa: BLE001 - degrade silently when the database is not ready
        return None
    if row is None:
        return None
    data: list[list[str]] = json.loads(row[0])
    return data
