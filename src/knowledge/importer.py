# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re
import urllib.request
from pathlib import Path

from ..models.word import Word
from ..models.syllable import Syllable
from ..prosody.chinese import FINAL_TO_PARTS, CHINESE_INITIALS
from .vocabulary import init_db, insert_words, word_count

_DATA_DIR = Path(__file__).parent / "data"

_CEDICT_URLS = [
    "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
    "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip",
]
_CEDICT_RAW_FILENAME = "cedict_ts.u8"


def _ensure_data_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _download_file(url: str, dest: Path, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def _download_cedict() -> Path | None:
    _ensure_data_dir()
    raw_path = _DATA_DIR / _CEDICT_RAW_FILENAME
    if raw_path.exists() and raw_path.stat().st_size > 1000:
        return raw_path

    last_error = None
    for url in _CEDICT_URLS:
        try:
            is_gz = url.endswith(".gz")
            is_zip = url.endswith(".zip")
            dl_path = _DATA_DIR / (
                "cedict_tmp" + (".gz" if is_gz else ".zip" if is_zip else "")
            )

            _download_file(url, dl_path)

            if is_gz:
                import gzip

                with gzip.open(dl_path, "rb") as gz, open(raw_path, "wb") as out:
                    out.write(gz.read())
            elif is_zip:
                import zipfile

                with zipfile.ZipFile(dl_path, "r") as zf:
                    names = zf.namelist()
                    txt_name = next(
                        (n for n in names if n.endswith(".txt") or n.endswith(".u8")),
                        names[0],
                    )
                    with zf.open(txt_name) as zf_in, open(raw_path, "wb") as out:
                        out.write(zf_in.read())
            dl_path.unlink(missing_ok=True)

            if raw_path.stat().st_size > 1000:
                return raw_path
            raw_path.unlink(missing_ok=True)
        except Exception as e:
            last_error = e
            continue

    print(f"\n[StanzaWeaver] CC-CEDICT 自动下载失败。")
    print(f"  请手动从 https://www.mdbg.net/chinese/dictionary?page=cc-cedict 下载")
    print(f"  将解压后的 cedict_ts.u8 放置到:")
    print(f"  {_DATA_DIR}")
    if last_error:
        print(f"  错误详情: {last_error}")
    print()
    if raw_path.exists():
        raw_path.unlink(missing_ok=True)
    return None


def _parse_cedict_line(line: str) -> Word | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(" ", 2)
    if len(parts) < 2:
        return None
    simplified = parts[1]
    rest = parts[2] if len(parts) > 2 else ""

    pinyin_match = re.search(r"\[(.+?)\]", rest)
    meaning_match = re.search(r"/(.+?)/", rest)

    if not pinyin_match or not meaning_match:
        return None

    pinyin_text = pinyin_match.group(1)
    meaning = meaning_match.group(1)

    syllables_raw = pinyin_text.split()
    syllables = _parse_pinyin_syllables(syllables_raw)

    return Word(
        text=simplified,
        language="zh",
        syllables=syllables,
        pos="",
        meaning=meaning.replace("/", "; "),
    )


def _parse_pinyin_syllables(syllables_raw: list[str]) -> list[Syllable]:
    tone_map = {
        "1": "平", "2": "平", "3": "仄", "4": "仄", "5": "",
    }

    results = []
    for raw in syllables_raw:
        tone_num = ""
        base = raw.lower().rstrip("012345 ")
        if raw and raw[-1].isdigit():
            tone_num = raw[-1]
            base = raw[:-1].lower()
        elif raw and raw[-1] == " ":
            base = raw[:-1].lower()

        onset = ""
        final_part = base
        for init in sorted(CHINESE_INITIALS, key=len, reverse=True):
            if base.startswith(init) and base != init:
                onset = init
                final_part = base[len(init) :]
                break

        if final_part and final_part[0] in {"y", "w"} and not onset:
            final_part = final_part[1:]

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


def import_chinese(limit: int = 0):
    if word_count("zh") > 0:
        return
    path = _download_cedict()
    if path is None:
        return
    batch: list[Word] = []
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            word = _parse_cedict_line(line)
            if word is None:
                continue
            batch.append(word)
            count += 1
            if len(batch) >= 500:
                insert_words(batch)
                batch.clear()
            if limit > 0 and count >= limit:
                break
    if batch:
        insert_words(batch)


def import_english():
    if word_count("en") > 0:
        return
    try:
        import nltk

        nltk.data.find("corpora/cmudict.zip")
    except LookupError:
        nltk.download("cmudict", quiet=True)
    from nltk.corpus import cmudict

    batch: list[Word] = []
    for word, pronunciations in cmudict.dict().items():
        if not word.isalpha():
            continue
        phones = pronunciations[0]

        syllables = _parse_arpabet(phones)
        if not syllables:
            continue

        batch.append(
            Word(
                text=word.upper(),
                language="en",
                syllables=syllables,
                pos="",
                meaning="",
            )
        )
        if len(batch) >= 500:
            insert_words(batch)
            batch.clear()
    if batch:
        insert_words(batch)


_VOWEL_PHONEMES = {
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
_STRESS_MAP = {"0": "", "1": "heavy", "2": "light"}


def _parse_arpabet(phones: list[str]) -> list[Syllable]:
    syllables = []
    current_onset: list[str] = []
    current_nucleus = ""
    current_stress = ""
    current_coda: list[str] = []

    for phone in phones:
        clean = re.sub(r"\d+", "", phone)
        stress_match = re.search(r"\d", phone)
        stress = stress_match.group() if stress_match else ""

        if clean in _VOWEL_PHONEMES:
            if current_nucleus:
                syllables.append(
                    Syllable(
                        onset="".join(current_onset),
                        nucleus=current_nucleus,
                        coda="".join(current_coda),
                        attributes={"tone": "", "stress": current_stress, "length": ""},
                    )
                )
                current_onset = []
                current_coda = []
            current_nucleus = clean
            current_stress = _STRESS_MAP.get(stress, "")
        else:
            if current_nucleus:
                current_coda.append(clean)
            else:
                current_onset.append(clean)

    if current_nucleus:
        syllables.append(
            Syllable(
                onset="".join(current_onset),
                nucleus=current_nucleus,
                coda="".join(current_coda),
                attributes={"tone": "", "stress": current_stress, "length": ""},
            )
        )
    return syllables


def import_all(limit_chinese: int = 0):
    init_db()
    import_chinese(limit=limit_chinese)
    import_english()
