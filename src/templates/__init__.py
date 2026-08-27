"""格律模板基类与注册表。

模板（PoetryTemplate）定义一种诗体的全部格律规则：
- syllables_per_line: 每行音节数（int 或 (min, max) 区间）；
- get_syllable_constraints(): 逐位约束（供 refine_line 单行校验与 LLM 提示）；
- validate_full(): 完整规则检查（押韵、三平尾、孤平等跨行规则）；
- describe(): 给 LLM 的人类可读格律描述。
"""

from abc import ABC
from collections.abc import Sequence
from typing import Any, ClassVar

from ..models.syllable import Syllable

SyllableCount = int | tuple[int, int]
ConstraintDict = dict[str, Any]
ConstraintLine = list[ConstraintDict]
ConstraintTable = list[ConstraintLine]


class PoetryTemplate(ABC):
    """格律模板基类（每种诗体一个子类）。"""

    name: ClassVar[str] = ""
    language: ClassVar[str] = ""
    lines: ClassVar[int] = 0
    # Sequence（协变）允许子类覆盖为 list[int] 或 list[tuple[int, int]]
    syllables_per_line: ClassVar[Sequence[SyllableCount]] = []
    rule_description: ClassVar[str] = ""

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """返回逐位音节约束表（每行一个约束列表）。

        Returns:
            约束表；不限定时返回 None。
        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """执行模板专属的完整规则检查。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表（analyze_line 结果）。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        return []

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（供校验器与前端使用）。

        Returns:
            {"name", "language", "lines", "syllables_per_line",
             "syllable_constraints"}。
        """
        return {
            "name": self.name,
            "language": self.language,
            "lines": self.lines,
            "syllables_per_line": list(self.syllables_per_line),
            "syllable_constraints": self.get_syllable_constraints(),
        }

    def describe(self) -> str:
        """生成给 AI 提示的人类可读格律描述。

        Returns:
            多行文本：行数、每行音节数、逐位约束、自然语言规则。
        """
        lines_desc = f"共 {self.lines} 行"
        for i, cnt in enumerate(self.syllables_per_line):
            constraints = self.get_syllable_constraints()
            line_info = f"  第{i + 1}行: {format_count(cnt)}音节"
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
        if self.rule_description:
            lines_desc += "\n" + self.rule_description
        return lines_desc


_registry: dict[str, PoetryTemplate] = {}


def register(key: str, template: PoetryTemplate) -> None:
    """注册模板到全局注册表。

    Args:
        key: 模板键（如 "zh_wujue"）。
        template: 模板实例。
    """
    _registry[key] = template


def format_count(cnt: SyllableCount) -> str:
    """格式化音节数供提示/报错使用。

    Args:
        cnt: int 定值或 (min, max) 区间。

    Returns:
        "5" 或 "15-17"。
    """
    if isinstance(cnt, (tuple, list)) and len(cnt) == 2:
        return f"{cnt[0]}-{cnt[1]}"
    return str(cnt)


def get(key: str) -> PoetryTemplate:
    """按键获取模板。

    Args:
        key: 模板键。

    Returns:
        模板实例。

    Raises:
        KeyError: 键未注册。
    """
    return _registry[key]


def list_all() -> list[PoetryTemplate]:
    """返回全部已注册模板。

    Returns:
        模板实例列表。
    """
    return list(_registry.values())


_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "汉语",
    "en": "英语",
    "it": "意大利语",
    "fr": "法语",
    "la": "古典拉丁语",
}


def list_dicts() -> list[dict[str, Any]]:
    """返回全部模板的字典形式（含显示名），供前端下拉列表使用。

    Returns:
        [{"key", "name", "language", "lines", "syllables_per_line",
          "syllable_constraints", "display_name"}, ...]。
    """
    return [
        {
            "key": k,
            **t.to_dict(),
            "display_name": f"{t.name}（{_LANGUAGE_LABELS.get(t.language, t.language)}）",
        }
        for k, t in _registry.items()
    ]
