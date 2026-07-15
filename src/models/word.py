# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
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
            "syllables": [s.to_dict() for s in self.syllables] if self.syllables else [],
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
