# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..models.word import Word
from ..models.syllable import Syllable


SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_DB_PATH: Optional[Path] = None


def set_db_path(path: Path):
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path.home() / ".stanza_weaver" / "vocabulary.db"
    return _DB_PATH


def init_db():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.close()


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(str(get_db_path()))


def insert_word(word: Word):
    insert_words([word])


def insert_words(words: list[Word]):
    conn = _get_conn()
    rows = []
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


def _syl_from_json(d: dict) -> Syllable:
    attrs = d.get("attributes", {})
    return Syllable(
        onset=d.get("onset", ""),
        nucleus=d.get("nucleus", ""),
        coda=d.get("coda", ""),
        attributes={
            "tone": attrs.get("tone", ""),
            "stress": attrs.get("stress", ""),
            "length": attrs.get("length", ""),
        },
    )


def _syl_matches(
    syl: Syllable, onset="", nucleus="", coda="", tone="", stress="", length=""
) -> bool:
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
    if length and syl.attributes.get("length", "") != length:
        return False
    return True


def search_words(
    language: str,
    query: str = "",
    syllable_count: Optional[int] = None,
    onset: str = "",
    nucleus: str = "",
    coda: str = "",
    tone: str = "",
    stress: str = "",
    length: str = "",
    limit: int = 20,
) -> list[dict]:
    conn = _get_conn()
    conditions = ["language = ?"]
    params: list = [language]

    if syllable_count is not None:
        conditions.append("syllable_count = ?")
        params.append(syllable_count)

    where_clause = " AND ".join(conditions)
    sql = f"SELECT text, language, meaning, syllables_json, syllable_count FROM words WHERE {where_clause} LIMIT ?"
    params.append(
        limit * 4
        if not onset
        and not nucleus
        and not coda
        and not tone
        and not stress
        and not length
        else limit * 8
    )

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
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
                for _ in range(sc)
            ]

        match_idx = None
        if onset or nucleus or coda or tone or stress or length:
            for idx, s in enumerate(syllables):
                if _syl_matches(s, onset, nucleus, coda, tone, stress, length):
                    match_idx = idx
                    break
            if match_idx is None:
                continue

        results.append(
            {
                "text": text,
                "language": lang,
                "meaning": meaning,
                "syllables": [s.to_dict() for s in syllables],
                "matched_syllable": match_idx if match_idx is not None else None,
            }
        )
        if len(results) >= limit:
            break

    if query and results:
        from .embeddings import rerank

        results = rerank(query, results, top_k=limit)
    return results[:limit]


def word_count(language: str = "") -> int:
    conn = _get_conn()
    if language:
        count = conn.execute(
            "SELECT COUNT(*) FROM words WHERE language = ?", (language,)
        ).fetchone()[0]
    else:
        count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    conn.close()
    return count


def has_words(language: str = "") -> bool:
    return word_count(language) > 0
