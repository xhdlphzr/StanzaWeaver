# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Vocabulary dataset import (CC-CEDICT / CMUdict / Lexique / GLAW-IT / Lewis & Short).

Runs automatically on first launch: downloads datasets, parses them into Word
lists, and writes them to SQLite. A dataset already imported is skipped (the
meta table records the version).
"""

import re
import urllib.request
from logging import Logger

from ..logging_setup import get_logger
from ..models.syllable import Syllable
from ..models.word import Word
from ..prosody.chinese import CHINESE_INITIALS, FINAL_TO_PARTS
from .vocabulary import get_db_path, init_db, insert_words, set_en_pron

# Restore y/w zero-initial spellings to pypinyin-style finals so they stay
# consistent with the real-time analysis in prosody/chinese.py
_YW_MAP: dict[str, str] = {
    "yu": "ü",
    "yue": "üe",
    "yun": "ün",
    "yuan": "üan",
    "yi": "i",
    "ya": "ia",
    "yan": "ian",
    "yang": "iang",
    "yao": "iao",
    "ye": "ie",
    "yong": "iong",
    "you": "iu",
    "ying": "ing",
    "wu": "u",
    "wa": "ua",
    "wo": "uo",
    "wai": "uai",
    "wei": "ui",
    "wan": "uan",
    "wen": "uen",
    "wang": "uang",
    "weng": "ueng",
}

logger: Logger = get_logger(__name__)


def _download_text(url: str, timeout: int = 10) -> str | None:
    """Download a text resource (return None on failure).

    Network errors (URLError/HTTPError/timeout) are all OSError subclasses.

    Args:
        url: Resource URL.
        timeout: Timeout in seconds.

    Returns:
        Text content; None on failure.

    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return str(data)
    except OSError:
        return None


def _dataset_key(name: str) -> str:
    """Return the dataset meta key.

    Args:
        name: Language code.

    Returns:
        "dataset_{lang}".

    """
    return f"dataset_{name}"


def _check_dataset(lang: str, expected: str) -> bool:
    """Check whether a dataset has already been imported.

    Args:
        lang: Language code.
        expected: Expected dataset name.

    Returns:
        True if already imported.

    """
    import sqlite3

    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    cur = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (_dataset_key(lang),)
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) FROM words WHERE language = ?", (lang,)
    ).fetchone()[0]
    conn.close()
    return bool(cur) and cur[0] == expected and int(count) > 0


def _set_dataset(lang: str, name: str) -> None:
    """Record the imported dataset version.

    Args:
        lang: Language code.
        name: Dataset name.

    """
    import sqlite3

    conn = sqlite3.connect(str(get_db_path()))
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (_dataset_key(lang), name),
    )
    conn.commit()
    conn.close()


def _import_chinese() -> None:
    """Import CC-CEDICT (Chinese entries).

    Each reading of a polyphonic character becomes its own record.
    """
    if _check_dataset("zh", "CC-CEDICT"):
        logger.info("[zh] data already present, skipping")
        return
    import gzip

    batch: list[Word] = []
    total = 0
    try:
        req = urllib.request.Request(
            "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = gzip.decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
    except OSError as e:
        # Network/decompression failure (URLError/HTTPError/BadGzipFile are all
        # OSError subclasses)
        logger.warning("[zh] CC-CEDICT error: %s", e)
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        simplified = parts[1]
        rest = parts[2] if len(parts) > 2 else ""
        # Extract every pinyin group (primary reading, variants, neutral tone,
        # etc.), not just the first
        pinyin_groups = re.findall(r"\[([^\[\]/]+?)\]", rest)
        meaning_match = re.search(r"/(.+?)/", rest)
        if not pinyin_groups:
            continue
        valid_prons: list[list[str]] = []
        for g in pinyin_groups:
            toks = g.split()
            if toks and all(
                re.fullmatch(r"[a-züv]+[1-5]?", t, re.IGNORECASE) for t in toks
            ):
                valid_prons.append(toks)
        if not valid_prons:
            continue
        meaning = (
            meaning_match.group(1).replace("/", "; ")[:120] if meaning_match else ""
        )
        seen_pron: set[tuple[str, ...]] = set()
        for toks in valid_prons:
            key = tuple(toks)
            if key in seen_pron:
                continue
            seen_pron.add(key)
            syls = _parse_pinyin(toks)
            batch.append(
                Word(text=simplified, language="zh", syllables=syls, meaning=meaning)
            )
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
    if batch:
        insert_words(batch)
    if total > 0:
        _set_dataset("zh", "CC-CEDICT")
    logger.info("[zh@CC-CEDICT] %d", total)


def _parse_pinyin(raw_list: list[str]) -> list[Syllable]:
    """Parse a list of pinyin syllables (with tone digits).

    Args:
        raw_list: e.g. ["ni3", "hao3"].

    Returns:
        Syllable list (the level/oblique label is stored under ``tone``).

    """
    tone_map: dict[str, str] = {"1": "平", "2": "平", "3": "仄", "4": "仄", "5": "平"}
    results: list[Syllable] = []
    for raw in raw_list:
        tone_num = ""
        base = raw.lower().rstrip("012 ")
        if raw and raw[-1].isdigit():
            tone_num = raw[-1]
            base = raw[:-1].lower()
        onset = ""
        final_part = base
        for init in sorted(CHINESE_INITIALS, key=len, reverse=True):
            if base.startswith(init) and base != init:
                onset = init
                final_part = base[len(init) :]
                break
        if not onset and (final_part.startswith(("y", "w"))):
            final_part = _YW_MAP.get(final_part, final_part[1:])
        nucleus, coda = FINAL_TO_PARTS.get(final_part, (final_part, ""))
        results.append(
            Syllable(
                onset=onset,
                nucleus=nucleus,
                coda=coda,
                attributes={
                    "tone": tone_map.get(tone_num, ""),
                    "stress": "",
                    "length": "",
                },
            )
        )
    return results


def _sqlite_delete(lang: str) -> None:
    """Delete word entries for one language.

    Args:
        lang: Language code.

    """
    import sqlite3

    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("DELETE FROM words WHERE language = ?", (lang,))
    conn.commit()
    conn.close()


# ── English: CMUdict ──


def _import_english() -> None:
    """Import CMUdict (English; each pronunciation variant becomes its own record).

    Secondary stress is recorded as ``heavy``.
    """
    if _check_dataset("en", "CMUdict"):
        logger.info("[en] data already present, skipping")
        return
    try:
        import nltk  # type: ignore[import-untyped]

        nltk.data.find("corpora/cmudict.zip")
    except LookupError:
        nltk.download("cmudict", quiet=True)
    from nltk.corpus import cmudict  # type: ignore[import-untyped]

    from ..prosody.english import EnglishAnalyzer

    en_analyzer = EnglishAnalyzer()
    batch: list[Word] = []
    total = 0
    for word, pron_list in cmudict.dict().items():
        key = str(word).lower()
        if not key.isalpha():
            continue
        seen: set[tuple[str, ...]] = set()
        pron_holder: list[list[str]] = []
        for phones in pron_list:
            phones_list = [str(p) for p in phones]
            pron_key = tuple(phones_list)
            if pron_key in seen:
                continue
            seen.add(pron_key)
            pron_holder.append(phones_list)
            syls = en_analyzer._parse_phones(phones_list)
            if syls:
                batch.append(Word(text=key, language="en", syllables=syls, meaning=""))
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
        if pron_holder:
            set_en_pron(key, pron_holder)
    if batch:
        insert_words(batch)
    if total > 0:
        _set_dataset("en", "CMUdict")
    logger.info("[en@CMUdict] %d", total)


# ── French: Lexique ──


def _import_french() -> None:
    """Import Lexique382 (French word forms).

    The real syllable structure is derived by FrenchAnalyzer.
    """
    from ..prosody.french import FrenchAnalyzer

    _fr_analyzer = FrenchAnalyzer()
    if _check_dataset("fr", "Lexique382"):
        logger.info("[fr] data already present, skipping")
        return
    text = _download_text(
        "http://www.lexique.org/databases/Lexique382/Lexique382.tsv", timeout=15
    )
    total = 0
    if text:
        lines = text.splitlines()
        if len(lines) > 1:
            hdr = lines[0].split("\t")
            wc = next((i for i, h in enumerate(hdr) if h.lower() == "ortho"), 0)
            sc = next(
                (i for i, h in enumerate(hdr) if h.lower() in ("nbsyl", "nbsyll")), -1
            )
            pc = next((i for i, h in enumerate(hdr) if h.lower() == "phon"), -1)
            seen: set[str] = set()
            batch: list[Word] = []
            for line in lines[1:]:
                cols = line.split("\t")
                if len(cols) <= wc:
                    continue
                w = cols[wc].strip().lower()
                if not w or w in seen:
                    continue
                seen.add(w)
                n = 1
                if sc >= 0 and sc < len(cols):
                    try:
                        n = int(cols[sc])
                    except ValueError:
                        n = 1
                phon = cols[pc] if pc >= 0 and pc < len(cols) else ""
                syls = _fr_analyzer._syllabify_word(w)
                n = max(n, 1)
                if not syls:
                    syls = [
                        Syllable(
                            nucleus="?",
                            attributes={"tone": "", "stress": "", "length": ""},
                        )
                        for _ in range(n)
                    ]
                elif len(syls) != n:
                    placeholder = Syllable(
                        nucleus="?",
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                    if len(syls) < n:
                        while len(syls) < n:
                            syls.append(placeholder)
                    else:
                        syls = syls[:n]
                batch.append(Word(text=w, language="fr", syllables=syls, meaning=phon))
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
            if batch:
                insert_words(batch)
    if total > 0:
        _set_dataset("fr", "Lexique382")
    logger.info("[fr@Lexique] %d", total)


# ── Italian: GLAW-IT ──

_GLAWIT_URL = "http://redac.univ-tlse2.fr/lexicons/glawit/glawit_2017-06-09.xml.bz2"


def _import_italian() -> None:
    """Import GLAW-IT (Italian word forms and meanings)."""
    if _check_dataset("it", "GLAW-IT"):
        logger.info("[it] data already present, skipping")
        return
    import bz2

    from ..prosody.italian import ItalianAnalyzer

    analyzer = ItalianAnalyzer()
    seen: set[str] = set()
    batch: list[Word] = []
    total = 0
    try:
        req = urllib.request.Request(_GLAWIT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            if raw[:3] == b"BZh":
                raw = bz2.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
    except OSError as e:
        # Network/decompression failure (URLError/HTTPError/OSError subclasses)
        logger.warning("[it] GLAW-IT error: %s", e)
        text = None
    if text:
        titles = list(re.finditer(r"<title>([^<]+)</title>", text))
        glosses = list(re.finditer(r"<txt>([^<]+)</txt>", text))
        gloss_idx = 0
        for tm in titles:
            w = tm.group(1).strip().lower()
            if not w or w in seen:
                continue
            seen.add(w)
            meaning = ""
            while gloss_idx < len(glosses) and glosses[gloss_idx].start() < tm.start():
                gloss_idx += 1
            if gloss_idx < len(glosses):
                meaning = glosses[gloss_idx].group(1).strip()[:120]
                gloss_idx += 1
            syls = analyzer._syllabify_word(w)
            if not syls:
                syls = [
                    Syllable(
                        nucleus="?",
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                    for _ in range(max(analyzer.count_syllables_in_word(w), 1))
                ]
            batch.append(Word(text=w, language="it", syllables=syls, meaning=meaning))
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
        for m in re.finditer(r'form="([^"]+)"', text):
            w = m.group(1).strip().lower()
            if w and w not in seen:
                seen.add(w)
                syls = analyzer._syllabify_word(w)
                if not syls:
                    syls = [
                        Syllable(
                            nucleus="?",
                            attributes={"tone": "", "stress": "", "length": ""},
                        )
                        for _ in range(max(analyzer.count_syllables_in_word(w), 1))
                    ]
                batch.append(Word(text=w, language="it", syllables=syls, meaning=""))
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
    if batch:
        insert_words(batch)
    if total > 0:
        _set_dataset("it", "GLAW-IT")
    logger.info("[it@GLAW-IT] %d", total)


# ── Latin: Lewis & Short ──

_LS_URL = "https://raw.githubusercontent.com/telemachus/plaintext-lewis-short/main/lewis-short.txt"


def _import_latin() -> None:
    """Import Lewis & Short (Latin entries).

    Vowel length is judged by orthographic heuristics.
    """
    if _check_dataset("la", "Lewis-Short"):
        logger.info("[la] data already present, skipping")
        return
    from ..prosody.latin import LatinAnalyzer

    analyzer = LatinAnalyzer()
    seen: set[str] = set()
    batch: list[Word] = []
    total = 0
    text = _download_text(_LS_URL, timeout=60)
    if text:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0] in "[({\"'":
                continue
            parts = line.split(None, 1)
            w = parts[0].strip().lower()
            clean = re.sub(r"[^a-zāēīōūȳăĕĭŏŭ]", "", w)
            if not clean or clean in seen:
                continue
            meaning = parts[1].strip()[:120] if len(parts) > 1 else ""
            seen.add(clean)
            syllables = analyzer.analyze_line(clean)
            if not syllables:
                syllables = [
                    Syllable(
                        nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                    )
                    for _ in range(len(clean))
                ]
            batch.append(
                Word(text=clean, language="la", syllables=syllables, meaning=meaning)
            )
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
    if batch:
        insert_words(batch)
    if total > 0:
        _set_dataset("la", "Lewis-Short")
    logger.info("[la@L&S] %d", total)


def import_all() -> None:
    """Import every language vocabulary (idempotent; imported datasets are skipped)."""
    init_db()
    logger.info("[StanzaWeaver] Importing vocabulary...")
    _import_chinese()
    _import_english()
    _import_french()
    _import_italian()
    _import_latin()
    logger.info("[StanzaWeaver] Ready")
