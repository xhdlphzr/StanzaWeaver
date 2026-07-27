# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
from ..knowledge.vocabulary import search_words as db_search


def execute_search_words(template: dict, arguments: dict) -> dict:
    language = template.get("language", "zh")
    meaning = arguments.get("meaning", "")
    syllable_count = arguments.get("syllable_count")
    onset = arguments.get("onset", "")
    nucleus = arguments.get("nucleus", "")
    coda = arguments.get("coda", "")
    tone = arguments.get("tone", "")
    stress = arguments.get("stress", "")
    length = arguments.get("length", "")
    pos = arguments.get("pos", "")
    limit = arguments.get("limit", 20)

    results = db_search(
        language=language,
        meaning=meaning,
        syllable_count=syllable_count,
        onset=onset,
        nucleus=nucleus,
        coda=coda,
        tone=tone,
        stress=stress,
        length=length,
        pos=pos,
        limit=limit,
    )
    return {"words": results}
