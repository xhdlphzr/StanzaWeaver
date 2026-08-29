# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""多语言统一音节计数与整行分析入口。

按语言路由到对应分析器；中文整行交给 pypinyin（上下文消歧多音字），
意大利语整行做 sinalefe 合并，其余语言逐词切分。
"""

from collections.abc import Callable
from typing import cast

from ..models.syllable import Syllable
from .base import SyllableAnalyzer
from .chinese import ChineseAnalyzer
from .english import EnglishAnalyzer
from .french import FrenchAnalyzer
from .italian import ItalianAnalyzer
from .latin import LatinAnalyzer

_ANALYZERS: dict[str, SyllableAnalyzer] = {
    "zh": ChineseAnalyzer(),
    "en": EnglishAnalyzer(),
    "it": ItalianAnalyzer(),
    "fr": FrenchAnalyzer(),
    "la": LatinAnalyzer(),
}

_LineHandler = Callable[[SyllableAnalyzer, str], list[Syllable]]


def _zh_line(analyzer: SyllableAnalyzer, line: str) -> list[Syllable]:
    """中文整行分析：取多音字消歧后的首选变体。

    Args:
        analyzer: 中文分析器。
        line: 一行诗。

    Returns:
        首选音节切分。
    """
    variants = analyzer.analyze_line_variants(line)  # type: ignore[attr-defined]
    for v in variants:
        if v:
            return cast("list[Syllable]", v)
    return []


def _it_line(analyzer: SyllableAnalyzer, line: str) -> list[Syllable]:
    """意大利语整行分析（含 sinalefe 合并）。

    Args:
        analyzer: 意大利语分析器。
        line: 一行诗。

    Returns:
        整行音节列表。
    """
    return cast("list[Syllable]", analyzer.syllabify_line(line))  # type: ignore[attr-defined]


def _la_line(analyzer: SyllableAnalyzer, line: str) -> list[Syllable]:
    """拉丁语整行分析（跨词音长判定）。

    Args:
        analyzer: 拉丁语分析器。
        line: 一行诗。

    Returns:
        整行音节列表。
    """
    return cast("list[Syllable]", analyzer.analyze_line(line))  # type: ignore[attr-defined]


_LINE_HANDLERS: dict[str, _LineHandler] = {
    "zh": _zh_line,
    "it": _it_line,
    "la": _la_line,
}


def register_analyzer(language: str, analyzer: SyllableAnalyzer) -> None:
    """注册（或覆盖）某语言的分析器。

    Args:
        language: 语言代码（zh/en/it/fr/la）。
        analyzer: 分析器实例。
    """
    _ANALYZERS[language] = analyzer


def get_analyzer(language: str) -> SyllableAnalyzer:
    """按语言获取分析器。

    Args:
        language: 语言代码。

    Returns:
        对应分析器实例。

    Raises:
        ValueError: 未注册该语言。
    """
    if language in _ANALYZERS:
        return _ANALYZERS[language]
    raise ValueError(f"No syllable analyzer registered for language: {language}")


def count_syllables(text: str, language: str) -> int:
    """统计文本音节数。

    Args:
        text: 任意文本。
        language: 语言代码。

    Returns:
        音节总数。
    """
    return get_analyzer(language).count_syllables(text)


def analyze_line(line: str, language: str) -> list[Syllable]:
    """分析一行的全部音节。

    中文整行分析（多音字按上下文消歧）；意大利语含 sinalefe 合并；
    其余语言逐词分析后拼接。

    Args:
        line: 一行诗。
        language: 语言代码。

    Returns:
        整行音节列表。
    """
    analyzer = get_analyzer(language)
    handler = _LINE_HANDLERS.get(language)
    if handler is not None:
        return handler(analyzer, line)
    words = analyzer.tokenize_line(line)
    syllables: list[Syllable] = []
    for w in words:
        analyzed = analyzer.analyze_word(w)
        syllables.extend(analyzed)
    return syllables
