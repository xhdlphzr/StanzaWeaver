# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from ..knowledge.vocabulary import search_words as db_search


def execute_search_words(template: dict, arguments: dict) -> dict:
    language = template.get("language", "zh")
    syllable_count = arguments.get("syllable_count")
    onset = arguments.get("onset", "")
    nucleus = arguments.get("nucleus", "")
    coda = arguments.get("coda", "")
    tone = arguments.get("tone", "")
    stress = arguments.get("stress", "")
    length = arguments.get("length", "")
    limit = arguments.get("limit", 20)

    results = db_search(
        language=language,
        syllable_count=syllable_count,
        onset=onset,
        nucleus=nucleus,
        coda=coda,
        tone=tone,
        stress=stress,
        length=length,
        limit=limit,
    )
    return {"words": results}
