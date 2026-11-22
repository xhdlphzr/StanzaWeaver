# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Abstract base class for syllable analyzers.

Each language implements the SyllableAnalyzer interface, providing:
- analyze_word: word -> syllable list (with tone/stress/length attributes)
- count_syllables: text -> total syllable count
- tokenize_line: line text -> words/characters (whitespace split by default)
"""

from abc import ABC, abstractmethod

from ..models.syllable import Syllable


class SyllableAnalyzer(ABC):
    """Syllable analyzer interface (one implementation per language)."""

    language: str = ""

    @abstractmethod
    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze the syllable division and phonological attributes of a word.

        Args:
            word: Word text.

        Returns:
            List of syllables; an empty list for an empty string or no valid
            syllables.

        """

    def count_syllables(self, text: str) -> int:
        """Count the total syllables in a text (first whole-line variant).

        By default this delegates to :meth:`analyze_line_variants` so that
        counting and meter validation share the same line-level division;
        subclasses only need to implement ``analyze_word`` /
        ``analyze_line_variants``.

        Args:
            text: Arbitrary text (may be multiple words or a whole line).

        Returns:
            Syllable count (non-negative integer).

        """
        variants = self.analyze_line_variants(text)
        return len(variants[0]) if variants else 0

    def tokenize_line(self, line: str) -> list[str]:
        """Split a line into analyzable units (words or characters).

        Args:
            line: One line of verse.

        Returns:
            List of units; whitespace split by default, overridden by the
            Chinese analyzer to split per character.

        """
        return line.split()

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Analyze all syllable division variants of a line.

        The default implementation concatenates the per-word analyses into a
        single variant. Subclasses may override it to combine variants for
        polyphonic characters or multiple divisions (e.g. pypinyin
        disambiguation for Chinese).

        Args:
            line: One line of verse.

        Returns:
            List of variants, each being the syllable list of the line.

        """
        words = self.tokenize_line(line)
        syllables: list[Syllable] = []
        for w in words:
            syllables.extend(self.analyze_word(w))
        return [syllables] if syllables else []
