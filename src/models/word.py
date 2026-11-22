# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Data model: word entry.

Representation of one word entry in the vocabulary database (SQLite): text,
language, syllable segmentation, and meaning. Chinese and English imports each
take one record; polyphonic characters get one record per reading.
"""

from dataclasses import dataclass, field
from typing import Any

from .syllable import Syllable

SyllableInput = Syllable | dict[str, Any]


@dataclass
class Word:
    """A word entry.

    Attributes:
        text: Entry text (uppercased for English, kept as-is for Chinese).
        language: Language code (zh/en/it/fr/la).
        syllables: Syllable segmentation list.
        meaning: Meaning (Chinese entries come from CC-CEDICT).

    """

    text: str
    language: str
    syllables: list[Syllable] = field(default_factory=list)
    meaning: str = ""

    @property
    def syllable_count(self) -> int:
        """Return the number of syllables.

        Returns:
            Length of the ``syllables`` list.

        """
        return len(self.syllables)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the word to a dictionary (with syllables as dicts).

        Returns:
            ``{"text": ..., "language": ..., "syllables": [...], "meaning": ...}``.

        """
        return {
            "text": self.text,
            "language": self.language,
            "syllables": [s.to_dict() for s in self.syllables]
            if self.syllables
            else [],
            "meaning": self.meaning,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Word:
        """Rebuild a word entry from a dictionary (inverse of :meth:`to_dict`).

        Args:
            d: Dictionary produced by ``to_dict()``.

        Returns:
            The reconstructed Word instance.

        """
        syllables: list[Syllable] = []
        for s in d.get("syllables", []):
            if isinstance(s, Syllable):
                syllables.append(s)
            elif isinstance(s, dict):
                syllables.append(Syllable.from_dict(s))
        return cls(
            text=str(d.get("text", "")),
            language=str(d.get("language", "")),
            syllables=syllables,
            meaning=str(d.get("meaning", "")),
        )
