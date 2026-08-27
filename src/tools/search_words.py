"""search_words 工具执行：按约束查询词库并返回候选词。"""

from typing import Any

from ..knowledge.vocabulary import search_words as db_search


def execute_search_words(
    template: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """执行候选词搜索。

    Args:
        template: 模板字典（提供语言）。
        arguments: 工具参数（query/音节数/逐位约束/limit）。

    Returns:
        {"words": [词条字典, ...]}。
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
    except (TypeError, ValueError):
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
