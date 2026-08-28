# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""词库数据集导入（CC-CEDICT / CMUdict / Lexique / GLAW-IT / Lewis & Short）。

首次运行自动执行：下载数据集 → 解析为 Word 列表 → 写入 SQLite。
同一数据集已导入时跳过（meta 表记录版本）。
"""

import re
import urllib.request
from logging import Logger

from ..logging_setup import get_logger
from ..models.syllable import Syllable
from ..models.word import Word
from ..prosody.chinese import CHINESE_INITIALS, FINAL_TO_PARTS
from .vocabulary import get_db_path, init_db, insert_words

# y/w 零声母拼写还原为 pypinyin 风格的韵母（与 prosody/chinese.py 实时分析保持一致）
_YW_MAP: dict[str, str] = {
    "yu": "ü", "yue": "üe", "yun": "ün", "yuan": "üan",
    "yi": "i", "ya": "ia", "yan": "ian", "yang": "iang", "yao": "iao",
    "ye": "ie", "yong": "iong", "you": "iu", "ying": "ing",
    "wu": "u", "wa": "ua", "wo": "uo", "wai": "uai", "wei": "ui",
    "wan": "uan", "wen": "uen", "wang": "uang", "weng": "ueng",
}

logger: Logger = get_logger(__name__)


def _download_text(url: str, timeout: int = 10) -> str | None:
    """下载文本资源（失败返回 None）。

    网络错误（URLError/HTTPError/超时）均为 OSError 子类。

    Args:
        url: 资源地址。
        timeout: 超时秒数。

    Returns:
        文本内容；失败时 None。
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return str(data)
    except OSError:
        return None


def _dataset_key(name: str) -> str:
    """数据集 meta 键。

    Args:
        name: 语言代码。

    Returns:
        "dataset_{lang}"。
    """
    return f"dataset_{name}"


def _check_dataset(lang: str, expected: str) -> bool:
    """判断数据集是否已导入。

    Args:
        lang: 语言代码。
        expected: 期望的数据集名。

    Returns:
        已导入返回 True。
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
    """记录已导入的数据集版本。

    Args:
        lang: 语言代码。
        name: 数据集名。
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
    """导入 CC-CEDICT（中文词条，多音字每个读音独立成条）。"""
    if _check_dataset("zh", "CC-CEDICT"):
        logger.info("[zh] 已有数据，跳过")
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
        # 网络/解压失败（URLError/HTTPError/BadGzipFile 均为 OSError 子类）
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
        # 提取所有拼音括号（主读音 + 异读 + 轻声等），而非仅第一个
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
        meaning = meaning_match.group(1).replace("/", "; ")[:120] if meaning_match else ""
        seen_pron: set[tuple[str, ...]] = set()
        for toks in valid_prons:
            key = tuple(toks)
            if key in seen_pron:
                continue
            seen_pron.add(key)
            syls = _parse_pinyin(toks)
            if not syls:
                continue
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
    """解析拼音音节列表（含声调数字）。

    Args:
        raw_list: 如 ["ni3", "hao3"]。

    Returns:
        音节列表（平仄标在 tone）。
    """
    tone_map: dict[str, str] = {"1": "平", "2": "平", "3": "仄", "4": "仄", "5": ""}
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
        if not nucleus and final_part:
            nucleus = final_part
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
    """删除某语言的词条。

    Args:
        lang: 语言代码。
    """
    import sqlite3

    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("DELETE FROM words WHERE language = ?", (lang,))
    conn.commit()
    conn.close()


# ── English: CMUdict ──


def _import_english() -> None:
    """导入 CMUdict（英文，全部发音变体独立成条，次重音记 heavy）。"""
    if _check_dataset("en", "CMUdict"):
        logger.info("[en] 已有数据，跳过")
        return
    try:
        import nltk  # type: ignore[import-untyped]

        nltk.data.find("corpora/cmudict.zip")
    except LookupError:
        nltk.download("cmudict", quiet=True)
    from nltk.corpus import cmudict  # type: ignore[import-untyped]

    batch: list[Word] = []
    total = 0
    _VOWELS = {
        "AA",
        "AE",
        "AH",
        "AO",
        "AW",
        "AX",
        "AXR",
        "AY",
        "EH",
        "ER",
        "EY",
        "IH",
        "IX",
        "IY",
        "OW",
        "OY",
        "UH",
        "UW",
        "UX",
    }
    _SMAP: dict[str, str] = {"0": "light", "1": "heavy", "2": "heavy"}
    for word, pron_list in cmudict.dict().items():
        if not str(word).isalpha():
            continue
        seen: set[tuple[str, ...]] = set()
        for phones in pron_list:
            pron_key: tuple[str, ...] = tuple(str(p) for p in phones)
            if pron_key in seen:
                continue
            seen.add(pron_key)
            syls: list[Syllable] = []
            ons: list[str] = []
            nuc = ""
            stre = ""
            cod: list[str] = []
            for p in phones:
                cl = re.sub(r"\d+", "", p)
                sm = re.search(r"\d", p)
                st = sm.group() if sm else ""
                if cl in _VOWELS:
                    if nuc:
                        syls.append(
                            Syllable(
                                onset="".join(ons),
                                nucleus=nuc,
                                coda="".join(cod),
                                attributes={"tone": "", "stress": stre, "length": ""},
                            )
                        )
                        ons = []
                        cod = []
                    nuc = cl
                    stre = _SMAP.get(st, "")
                else:
                    (cod if nuc else ons).append(cl)
            if nuc:
                syls.append(
                    Syllable(
                        onset="".join(ons),
                        nucleus=nuc,
                        coda="".join(cod),
                        attributes={"tone": "", "stress": stre, "length": ""},
                    )
                )
            if syls:
                batch.append(
                    Word(
                        text=str(word).upper(),
                        language="en",
                        syllables=syls,
                        meaning="",
                    )
                )
                total += 1
                if len(batch) >= 500:
                    insert_words(batch)
                    batch.clear()
    if batch:
        insert_words(batch)
    if total > 0:
        _set_dataset("en", "CMUdict")
    logger.info("[en@CMUdict] %d", total)


# ── French: Lexique ──


def _import_french() -> None:
    """导入 Lexique382（法语词形，真实音节结构由 FrenchAnalyzer 推导）。"""
    from ..prosody.french import FrenchAnalyzer

    _fr_analyzer = FrenchAnalyzer()
    if _check_dataset("fr", "Lexique382"):
        logger.info("[fr] 已有数据，跳过")
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
                if not syls:
                    syls = [
                        Syllable(
                            nucleus="?",
                            attributes={"tone": "", "stress": "", "length": ""},
                        )
                        for _ in range(max(n, 1))
                    ]
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
    """导入 GLAW-IT（意大利语词形与释义）。"""
    if _check_dataset("it", "GLAW-IT"):
        logger.info("[it] 已有数据，跳过")
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
        # 网络/解压失败（URLError/HTTPError/OSError 子类）
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
                    for _ in range(max(analyzer._count_syllables_in_word(w), 1))
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
                        for _ in range(max(analyzer._count_syllables_in_word(w), 1))
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
    """导入 Lewis & Short（拉丁语词条，音长按正字法启发式判定）。"""
    if _check_dataset("la", "Lewis-Short"):
        logger.info("[la] 已有数据，跳过")
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
    """导入全部语言词库（幂等，已导入的数据集自动跳过）。"""
    init_db()
    logger.info("[StanzaWeaver] 导入词库...")
    _import_chinese()
    _import_english()
    _import_french()
    _import_italian()
    _import_latin()
    logger.info("[StanzaWeaver] 就绪")
