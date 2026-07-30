# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from ..models.syllable import Syllable


class PoetryTemplate(ABC):
    name: str = ""
    language: str = ""
    lines: int = 0
    syllables_per_line: list[int] = []

    def get_syllable_constraints(self) -> list[list[dict]] | None:
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        return []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "language": self.language,
            "lines": self.lines,
            "syllables_per_line": list(self.syllables_per_line),
            "syllable_constraints": self.get_syllable_constraints(),
        }

    def describe(self) -> str:
        """Human-readable description for AI prompts."""
        lines_desc = f"共 {self.lines} 行"
        for i, cnt in enumerate(self.syllables_per_line):
            constraints = self.get_syllable_constraints()
            line_info = f"  第{i + 1}行: {cnt}音节"
            if constraints and i < len(constraints):
                parts = []
                for j, c in enumerate(constraints[i]):
                    desc_parts = []
                    if c.get("onset"):
                        desc_parts.append(f"声母={c['onset']}")
                    if c.get("nucleus"):
                        desc_parts.append(f"韵母={c['nucleus']}")
                    if c.get("coda"):
                        desc_parts.append(f"韵尾={c['coda']}")
                    for k, v in c.get("attributes", {}).items():
                        if v:
                            desc_parts.append(f"{k}={v}")
                    if desc_parts:
                        parts.append(f"    第{j + 1}位: {','.join(desc_parts)}")
                if parts:
                    line_info += "\n" + "\n".join(parts)
            lines_desc += "\n" + line_info
        return lines_desc


_registry: dict[str, PoetryTemplate] = {}


def register(key: str, template: PoetryTemplate):
    _registry[key] = template


def get(key: str) -> PoetryTemplate:
    return _registry[key]


def list_all() -> list[PoetryTemplate]:
    return list(_registry.values())


_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "汉语",
    "en": "英语",
    "it": "意大利语",
    "fr": "法语",
    "la": "古典拉丁语",
}


def list_dicts() -> list[dict]:
    return [
        {
            "key": k,
            **t.to_dict(),
            "display_name": f"{t.name}（{_LANGUAGE_LABELS.get(t.language, t.language)}）",
        }
        for k, t in _registry.items()
    ]
