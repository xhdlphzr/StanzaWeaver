# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""数据模型：词条（Word）。

词库（SQLite）中一个词条的表示：文本、语言、音节切分及释义。
中文/英文导入的词条各占一条记录，多音字每个读音单独成条。
"""

from dataclasses import dataclass, field
from typing import Any

from .syllable import Syllable

SyllableInput = Syllable | dict[str, Any]


@dataclass
class Word:
    """一个词条。

    Attributes:
        text: 词条文本（英文为大写，中文原样）。
        language: 语言代码（zh/en/it/fr/la）。
        syllables: 音节切分列表。
        meaning: 释义（中文词条来自 CC-CEDICT）。
    """

    text: str
    language: str
    syllables: list[Syllable] = field(default_factory=list)
    meaning: str = ""

    @property
    def syllable_count(self) -> int:
        """返回音节数。"""
        return len(self.syllables)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（含 syllables 列表的字典形式）。

        Returns:
            {"text": ..., "language": ..., "syllables": [...], "meaning": ...}。
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
    def from_dict(cls, d: dict[str, Any]) -> "Word":
        """从字典重建词条（to_dict 的逆操作）。

        Args:
            d: to_dict() 产生的字典。

        Returns:
            还原后的 Word 实例。
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
