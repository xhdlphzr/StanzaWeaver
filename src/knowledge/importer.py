# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re
import urllib.request

from ..models.word import Word
from ..models.syllable import Syllable
from ..prosody.chinese import FINAL_TO_PARTS, CHINESE_INITIALS
from .vocabulary import init_db, insert_words, word_count


def _download_text(url: str, timeout: int = 10) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ── Chinese: CC-CEDICT ──

_CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"


def _import_chinese():
    if word_count("zh") > 0:
        print("  [zh] 已有数据，跳过")
        return
    import gzip
    batch: list[Word] = []
    total = 0
    try:
        req = urllib.request.Request(_CEDICT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = gzip.decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [zh] CC-CEDICT error: {e}")
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
        pinyin_match = re.search(r"\[(.+?)\]", rest)
        meaning_match = re.search(r"/(.+?)/", rest)
        if not pinyin_match or not meaning_match:
            continue
        syls = _parse_pinyin(pinyin_match.group(1).split())
        meaning = meaning_match.group(1).replace("/", "; ")[:120]
        batch.append(Word(text=simplified, language="zh", syllables=syls, meaning=meaning))
        total += 1
        if len(batch) >= 500:
            insert_words(batch)
            batch.clear()
    if batch:
        insert_words(batch)
    print(f"  [zh@CC-CEDICT] {total}")


def _parse_pinyin(raw_list: list[str]) -> list[Syllable]:
    tone_map = {"1": "平", "2": "平", "3": "仄", "4": "仄", "5": ""}
    results = []
    for raw in raw_list:
        tone_num = ""
        base = raw.lower().rstrip("012345 ")
        if raw and raw[-1].isdigit():
            tone_num = raw[-1]
            base = raw[:-1].lower()
        onset = ""
        final_part = base
        for init in sorted(CHINESE_INITIALS, key=len, reverse=True):
            if base.startswith(init) and base != init:
                onset = init
                final_part = base[len(init):]
                break
        if final_part and final_part[0] in {"y", "w"} and not onset:
            final_part = final_part[1:]
        nucleus, coda = FINAL_TO_PARTS.get(final_part, (final_part, ""))
        if not nucleus and final_part:
            nucleus = final_part
        results.append(Syllable(onset=onset, nucleus=nucleus, coda=coda,
                                 attributes={"tone": tone_map.get(tone_num, ""), "stress": "", "length": ""}))
    return results


# ── English: CMUdict ──

def _import_english():
    if word_count("en") > 0:
        print("  [en] 已有数据，跳过")
        return
    try:
        import nltk
        nltk.data.find("corpora/cmudict.zip")
    except LookupError:
        nltk.download("cmudict", quiet=True)
    from nltk.corpus import cmudict
    batch: list[Word] = []
    total = 0
    _VOWELS = {"AA", "AE", "AH", "AO", "AW", "AX", "AXR", "AY", "EH", "ER", "EY",
               "IH", "IX", "IY", "OW", "OY", "UH", "UW", "UX"}
    _SMAP = {"0": "", "1": "heavy", "2": "light"}
    for word, pron_list in cmudict.dict().items():
        if not word.isalpha():
            continue
        phones = pron_list[0]
        syls = []
        ons = []; nuc = ""; stre = ""; cod = []
        for p in phones:
            cl = re.sub(r"\d+", "", p)
            sm = re.search(r"\d", p)
            st = sm.group() if sm else ""
            if cl in _VOWELS:
                if nuc:
                    syls.append(Syllable(onset="".join(ons), nucleus=nuc, coda="".join(cod),
                                         attributes={"tone": "", "stress": stre, "length": ""}))
                    ons = []; cod = []
                nuc = cl; stre = _SMAP.get(st, "")
            else:
                (cod if nuc else ons).append(cl)
        if nuc:
            syls.append(Syllable(onset="".join(ons), nucleus=nuc, coda="".join(cod),
                                 attributes={"tone": "", "stress": stre, "length": ""}))
        if syls:
            batch.append(Word(text=word.upper(), language="en", syllables=syls, meaning=""))
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
    if batch:
        insert_words(batch)
    print(f"  [en@CMUdict] {total}")


# ── French: Lexique ──

def _import_french():
    if word_count("fr") > 0:
        print("  [fr] 已有数据，跳过")
        return
    text = _download_text("http://www.lexique.org/databases/Lexique382/Lexique382.tsv", timeout=15)
    total = 0
    if text:
        lines = text.splitlines()
        if len(lines) > 1:
            hdr = lines[0].split("\t")
            wc = next((i for i, h in enumerate(hdr) if h.lower() == "ortho"), 0)
            sc = next((i for i, h in enumerate(hdr) if h.lower() in ("nbsyl", "nbsyll")), -1)
            pc = next((i for i, h in enumerate(hdr) if h.lower() == "phon"), -1)
            seen = set()
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
                    try: n = int(cols[sc])
                    except ValueError: n = 1
                phon = cols[pc] if pc >= 0 and pc < len(cols) else ""
                syls = [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""}) for _ in range(n)]
                batch.append(Word(text=w, language="fr", syllables=syls, meaning=phon))
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
            if batch:
                insert_words(batch)
    print(f"  [fr@Lexique] {total}")


# ── Italian: GLAW-IT ──

_GLAWIT_URL = "http://redac.univ-tlse2.fr/lexicons/glawit/glawit_2017-06-09.xml.bz2"


def _import_italian():
    if word_count("it") > 0:
        print("  [it] 已有数据，跳过")
        return
    from ..prosody.italian import ItalianAnalyzer
    import bz2
    analyzer = ItalianAnalyzer()
    seen = set()
    batch: list[Word] = []
    total = 0
    try:
        req = urllib.request.Request(_GLAWIT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            if raw[:3] == b"BZh":
                raw = bz2.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [it] GLAW-IT error: {e}")
        text = None
    if text:
        titles = list(re.finditer(r'<title>([^<]+)</title>', text))
        glosses = list(re.finditer(r'<txt>([^<]+)</txt>', text))
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
            c = analyzer._count_syllables_in_word(w)
            syls = [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""}) for _ in range(max(c, 1))]
            batch.append(Word(text=w, language="it", syllables=syls, meaning=meaning))
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
        for m in re.finditer(r'form="([^"]+)"', text):
            w = m.group(1).strip().lower()
            if w and w not in seen:
                seen.add(w)
                c = analyzer._count_syllables_in_word(w)
                syls = [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""}) for _ in range(max(c, 1))]
                batch.append(Word(text=w, language="it", syllables=syls, meaning=""))
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
    if batch:
        insert_words(batch)
    print(f"  [it@GLAW-IT] {total}")


# ── Latin: Lewis & Short ──

_LS_URL = "https://raw.githubusercontent.com/telemachus/plaintext-lewis-short/main/lewis-short.txt"


def _import_latin():
    if word_count("la") > 0:
        print("  [la] 已有数据，跳过")
        return
    from ..prosody.latin import LatinAnalyzer
    analyzer = LatinAnalyzer()
    seen = set()
    batch: list[Word] = []
    total = 0
    text = _download_text(_LS_URL, timeout=60)
    if text:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0].isspace() or line[0] in "[({\"'":
                continue
            parts = line.split(None, 1)
            if not parts:
                continue
            w = parts[0].strip().lower()
            clean = re.sub(r"[^a-zāēīōūȳăĕĭŏŭ]", "", w)
            if not clean or clean in seen:
                continue
            meaning = parts[1].strip()[:120] if len(parts) > 1 else ""
            seen.add(clean)
            syllables = analyzer.analyze_word(clean)
            if not syllables:
                syllables = [Syllable(nucleus="?", attributes={"tone": "", "stress": "", "length": ""}) for _ in range(len(clean))]
            batch.append(Word(text=clean, language="la", syllables=syllables, meaning=meaning))
            total += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
    if batch:
        insert_words(batch)
    print(f"  [la@L&S] {total}")


def import_all():
    init_db()
    import sqlite3
    from pathlib import Path as _P
    conn = sqlite3.connect(str(_P.home() / ".stanza_weaver" / "vocabulary.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    cur_ver = conn.execute("SELECT value FROM meta WHERE key='vocab_version'").fetchone()
    conn.close()
    if cur_ver and cur_ver[0] == "1":
        return
    print("[StanzaWeaver] 导入词库...")
    _import_chinese()
    _import_english()
    _import_french()
    _import_italian()
    _import_latin()
    conn = sqlite3.connect(str(_P.home() / ".stanza_weaver" / "vocabulary.db"))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('vocab_version', '1')")
    conn.commit()
    conn.close()
    print(f"[StanzaWeaver] 就绪")
