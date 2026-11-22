# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""search_words tool execution: query the vocabulary and return candidates."""

from typing import Any

from ..knowledge.vocabulary import search_words as db_search


def execute_search_words(
    template: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute candidate-word search.

    Args:
        template: Template dictionary (provides the language).
        arguments: Tool arguments (query / syllable count / positional
            constraints / limit).

    Returns:
        ``{"words": [word dictionary, ...]}``.

    """
    language = str(template.get("language", "zh"))
    query = str(arguments.get("query", ""))
    syllable_count = arguments.get("syllable_count")
    if not isinstance(syllable_count, int):
        syllable_count = None
    onset = str(arguments.get("onset", ""))
    nucleus = str(arguments.get("nucleus", ""))
    coda = str(arguments.get("coda", ""))
    tone = str(arguments.get("tone", ""))
    stress = str(arguments.get("stress", ""))
    length = str(arguments.get("length", ""))
    try:
        limit = max(1, min(int(arguments.get("limit", 20)), 50))
    except TypeError, ValueError:
        limit = 20

    results = db_search(
        language=language,
        query=query,
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
