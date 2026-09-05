# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""词库访问层（SQLite）。

- 词条表 words：文本、语言、释义、音节 JSON、音节数；
- search_words：按语言/音节数/逐位约束查询，支持向量相似度重排；
- 数据库默认位于 ~/.stanza_weaver/vocabulary.db。
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
    """覆盖数据库路径（主要供测试使用）。

    Args:
        path: 新的数据库文件路径。
    """
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> Path:
    """返回数据库路径（默认 ~/.stanza_weaver/vocabulary.db）。

    Returns:
        数据库文件路径。
    """
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path.home() / ".stanza_weaver" / "vocabulary.db"
    return _DB_PATH


def init_db() -> None:
    """初始化数据库（建表与索引，幂等）。"""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.close()


def _get_conn() -> sqlite3.Connection:
    """打开数据库连接。

    Returns:
        sqlite3 连接。
    """
    return sqlite3.connect(str(get_db_path()))


def insert_word(word: Word) -> None:
    """插入单个词条（便捷封装，主要供测试使用）。

    Args:
        word: 词条。
    """
    insert_words([word])


def insert_words(words: list[Word]) -> None:
    """批量插入词条。

    Args:
        words: 词条列表。
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
    """从字典还原音节。

    Args:
        d: 音节字典。

    Returns:
        Syllable 实例。
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
    """判断音节是否满足约束（空字段不限）。

    Args:
        syl: 音节。
        onset: onset 约束（空=不限）。
        nucleus: nucleus 约束（空=不限）。
        coda: coda 约束（空=不限）。
        tone: 声调约束（空=不限）。
        stress: 重音约束（空=不限）。
        length: 音长约束（空=不限）。

    Returns:
        满足返回 True。
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
    """按约束搜索候选词。

    约束匹配词内任一音节位（结果标注 matched_syllable）；
    提供 query 时用向量相似度重排。

    Args:
        language: 语言代码。
        query: 语义查询文本（用于重排，可为空）。
        syllable_count: 音节数约束。
        onset: onset 约束（空=不限）。
        nucleus: nucleus 约束（空=不限）。
        coda: coda 约束（空=不限）。
        tone: 声调约束（空=不限）。
        stress: 重音约束（空=不限）。
        length: 音长约束（空=不限）。
        limit: 最大返回数。

    Returns:
        词条字典列表。
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
    """统计词条数量（主要供 has_words 与测试使用）。

    Args:
        language: 语言代码（空=全部）。

    Returns:
        词条数。
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
    """判断词库是否非空（主要供测试使用）。

    Args:
        language: 语言代码（空=全部）。

    Returns:
        非空返回 True。
    """
    return word_count(language) > 0


def set_en_pron(word: str, prons: list[list[str]]) -> None:
    """写入英文词的 CMUdict 全部发音（本地缓存，供 EnglishAnalyzer 离线使用）。

    Args:
        word: 小写英文词。
        prons: 音素列表的列表（每个元素是一个发音）。
    """
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO en_pron (word, phones_json) VALUES (?, ?)",
        (word, json.dumps(prons, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_en_pron(word: str) -> list[list[str]] | None:
    """读取英文词的 CMUdict 全部发音（本地缓存）。

    Args:
        word: 小写英文词。

    Returns:
        音素列表的列表；词不存在于本地缓存或表尚未创建时返回 None
        （调用方应回退到 CMUdict）。
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT phones_json FROM en_pron WHERE word = ?", (word,)
        ).fetchone()
        conn.close()
    except Exception:  # noqa: BLE001 - 数据库未初始化时静默降级
        return None
    if row is None:
        return None
    data: list[list[str]] = json.loads(row[0])
    return data
