# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""音节分析器抽象基类。

每种语言实现 SyllableAnalyzer 接口，提供：
- analyze_word: 单词 → 音节列表（含平仄/重音/长短属性）
- count_syllables: 文本 → 音节总数
- tokenize_line: 行文本 → 分词/分字（默认按空白切分）
"""

from abc import ABC, abstractmethod

from ..models.syllable import Syllable


class SyllableAnalyzer(ABC):
    """音节分析器接口（每种语言一个实现）。"""

    language: str = ""

    @abstractmethod
    def analyze_word(self, word: str) -> list[Syllable]:
        """分析一个单词的音节切分与音系属性。

        Args:
            word: 单词文本。

        Returns:
            音节列表；空串或无有效音节时返回空列表。
        """

    def count_syllables(self, text: str) -> int:
        """统计一段文本的音节总数（取整行分析的首个变体）。

        默认委托 :meth:`analyze_line_variants`，使计数与格律校验使用同一
        行级切分口径；子类只需实现 ``analyze_word``/``analyze_line_variants``。

        Args:
            text: 任意文本（可为多词或整行）。

        Returns:
            音节数量（非负整数）。
        """
        variants = self.analyze_line_variants(text)
        return len(variants[0]) if variants else 0

    def tokenize_line(self, line: str) -> list[str]:
        """将一行文本切分为可分析的单元（词或字）。

        Args:
            line: 一行诗。

        Returns:
            单元列表；默认按空白切分，中文分析器覆写为逐字。
        """
        return line.split()

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """分析一行的全部音节切分变体。

        默认实现逐词分析后拼接为单一变体。子类可覆写以提供
        多音字/多切分的变体组合（如中文 pypinyin 多音字消歧）。

        Args:
            line: 一行诗。

        Returns:
            变体列表，每个变体是该行的音节列表。
        """
        words = self.tokenize_line(line)
        syllables: list[Syllable] = []
        for w in words:
            syllables.extend(self.analyze_word(w))
        return [syllables] if syllables else []
