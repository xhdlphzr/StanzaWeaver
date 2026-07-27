# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field
from .syllable import Syllable


@dataclass
class Word:
    text: str
    language: str
    syllables: list = field(default_factory=list)
    pos: str = ""
    meaning: str = ""

    @property
    def syllable_count(self) -> int:
        return len(self.syllables)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "syllables": [s.to_dict() for s in self.syllables]
            if self.syllables
            else [],
            "pos": self.pos,
            "meaning": self.meaning,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        syllables = []
        for s in d.get("syllables", []):
            if isinstance(s, Syllable):
                syllables.append(s)
            else:
                syllables.append(Syllable.from_dict(s))
        return cls(
            text=d["text"],
            language=d.get("language", ""),
            syllables=syllables,
            pos=d.get("pos", ""),
            meaning=d.get("meaning", ""),
        )
