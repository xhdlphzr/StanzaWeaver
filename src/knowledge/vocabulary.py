# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import sqlite3
from pathlib import Path
from typing import Optional

from ..models.word import Word
from ..models.syllable import Syllable
from ..prosody.syllable_counter import analyze_line


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
    conn.commit()
    conn.close()


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(str(get_db_path()))


def insert_word(word: Word):
    conn = _get_conn()
    syllables = word.syllables
    if syllables:
        s0 = syllables[0]
        onset = s0.onset
        nucleus = s0.nucleus
        coda = s0.coda
        tone = s0.attributes.get("tone", "")
        stress = s0.attributes.get("stress", "")
        length = s0.attributes.get("length", "")
        syl_count = len(syllables)
    else:
        onset = nucleus = coda = tone = stress = length = ""
        syl_count = 0

    conn.execute(
        """INSERT INTO words (text, language, pos, meaning, onset, nucleus, coda, tone, stress, length, syllable_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (word.text, word.language, word.pos, word.meaning, onset, nucleus, coda, tone, stress, length, syl_count),
    )
    conn.commit()
    conn.close()


def insert_words(words: list[Word]):
    conn = _get_conn()
    rows = []
    for word in words:
        syllables = word.syllables
        if syllables:
            s0 = syllables[0]
            onset = s0.onset
            nucleus = s0.nucleus
            coda = s0.coda
            tone = s0.attributes.get("tone", "")
            stress = s0.attributes.get("stress", "")
            length = s0.attributes.get("length", "")
            syl_count = len(syllables)
        else:
            onset = nucleus = coda = tone = stress = length = ""
            syl_count = 0
        rows.append((word.text, word.language, word.pos, word.meaning, onset, nucleus, coda, tone, stress, length, syl_count))

    conn.executemany(
        """INSERT INTO words (text, language, pos, meaning, onset, nucleus, coda, tone, stress, length, syllable_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


def search_words(
    language: str,
    meaning: str = "",
    syllable_count: Optional[int] = None,
    onset: str = "",
    nucleus: str = "",
    coda: str = "",
    tone: str = "",
    stress: str = "",
    length: str = "",
    pos: str = "",
    limit: int = 20,
) -> list[dict]:
    conn = _get_conn()
    conditions = ["language = ?"]
    params = [language]

    if meaning:
        conditions.append("(meaning LIKE ? OR text LIKE ?)")
        params.extend([f"%{meaning}%", f"%{meaning}%"])

    if syllable_count is not None:
        conditions.append("syllable_count = ?")
        params.append(syllable_count)

    if onset:
        conditions.append("onset = ?")
        params.append(onset)

    if nucleus:
        conditions.append("nucleus = ?")
        params.append(nucleus)

    if coda:
        conditions.append("coda = ?")
        params.append(coda)

    if tone:
        conditions.append("tone = ?")
        params.append(tone)

    if stress:
        conditions.append("stress = ?")
        params.append(stress)

    if length:
        conditions.append("length = ?")
        params.append(length)

    if pos:
        conditions.append("pos = ?")
        params.append(pos)

    where_clause = " AND ".join(conditions)
    query = f"SELECT text, language, pos, meaning, onset, nucleus, coda, tone, stress, length, syllable_count FROM words WHERE {where_clause} LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for row in rows:
        text, lang, p, m, ons, nuc, cod, ton, stre, leng, sc = row
        syl = Syllable(
            onset=ons,
            nucleus=nuc,
            coda=cod,
            attributes={"tone": ton, "stress": stre, "length": leng},
        )
        syllables = [syl] * sc
        results.append({
            "text": text,
            "language": lang,
            "pos": p,
            "meaning": m,
            "syllables": [s.to_dict() for s in syllables],
        })
    return results


def word_count(language: str = "") -> int:
    conn = _get_conn()
    if language:
        count = conn.execute("SELECT COUNT(*) FROM words WHERE language = ?", (language,)).fetchone()[0]
    else:
        count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    conn.close()
    return count


def has_words(language: str = "") -> bool:
    return word_count(language) > 0
