# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""多语言统一音节计数与整行分析入口。.

按语言路由到对应分析器，统一以 ``analyze_line_variants`` 为唯一行级口径：
中文整行交给 pypinyin（上下文消歧多音字），意大利语整行做 sinalefe 合并，
法语整行做跨词联诵，拉丁语整行做省音与跨词音长，其余语言逐词切分。
"""

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


def register_analyzer(language: str, analyzer: SyllableAnalyzer) -> None:
    """注册（或覆盖）某语言的分析器。.

    Args:
        language: 语言代码（zh/en/it/fr/la）。
        analyzer: 分析器实例。

    """
    _ANALYZERS[language] = analyzer


def get_analyzer(language: str) -> SyllableAnalyzer:
    """按语言获取分析器。.

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
    """统计文本音节数（与整行分析同口径）。.

    Args:
        text: 任意文本。
        language: 语言代码。

    Returns:
        音节总数。

    """
    return len(analyze_line(text, language))


def analyze_line(line: str, language: str) -> list[Syllable]:
    """分析一行的音节（取 ``analyze_line_variants`` 的首个非空变体）。.

    各语言的行级特性（中文多音字消歧、意大利语 sinalefe、法语联诵、
    拉丁语省音等）统一由各分析器的 ``analyze_line_variants`` 提供。

    Args:
        line: 一行诗。
        language: 语言代码。

    Returns:
        整行音节列表；无有效音节时返回空列表。

    """
    for variant in get_analyzer(language).analyze_line_variants(line):
        if variant:
            return variant
    return []
