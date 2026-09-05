# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""格律模板基类与注册表。

模板（PoetryTemplate）定义一种诗体的全部格律规则：
- syllables_per_line: 每行音节数（int 或 (min, max) 区间）；
- get_syllable_constraints(): 逐位约束（供 refine_line 单行校验与 LLM 提示）；
- validate_full(): 完整规则检查（押韵、三平尾等跨行规则）；
- describe(): 给 LLM 的人类可读格律描述。
"""

import re
from abc import ABC
from collections.abc import Sequence
from typing import Any, ClassVar

from ..models.syllable import Syllable

SyllableCount = int | tuple[int, int]
ConstraintDict = dict[str, Any]
ConstraintLine = list[ConstraintDict]
ConstraintTable = list[ConstraintLine]


def _make_syl(**kwargs: Any) -> dict[str, Any]:
    """构造逐位约束字典。

    Args:
        **kwargs: 可含 onset/nucleus/coda 及 attributes 子字典。

    Returns:
        约束字典（含完整 attributes 三键）。
    """
    attrs = kwargs.pop("attributes", {})
    if not isinstance(attrs, dict):
        attrs = {}
    return {
        "onset": kwargs.get("onset", ""),
        "nucleus": kwargs.get("nucleus", ""),
        "coda": kwargs.get("coda", ""),
        "attributes": {
            "tone": attrs.get("tone", ""),
            "stress": attrs.get("stress", ""),
            "length": attrs.get("length", ""),
        },
    }


def _last_word(line: str, allowed_chars: str) -> str:
    """取行末词（去标点、小写）。

    Args:
        line: 一行诗。
        allowed_chars: 正则字符类中允许的字符集（不含方括号）。

    Returns:
        行末词；空行返回空串。
    """
    if not line.strip():
        return ""
    return re.sub(rf"[^{allowed_chars}]", "", line.strip().split()[-1]).lower()


def describe_template_from_dict(template_dict: dict[str, Any]) -> str:
    """从模板字典生成格律描述（无模板对象时的降级方案）。

    Args:
        template_dict: 含 lines/syllables_per_line/syllable_constraints 的字典。

    Returns:
        多行格律描述文本。
    """
    lines_spec = template_dict.get("syllables_per_line", [])
    lines_desc = f"共 {template_dict.get('lines', len(lines_spec))} 行"
    constraints = template_dict.get("syllable_constraints") or []
    for i, cnt in enumerate(lines_spec):
        line_constraints = constraints[i] if i < len(constraints) else []
        line_info = f"  第{i + 1}行: {format_count(cnt)}音节"
        if line_constraints:
            parts = []
            for j, c in enumerate(line_constraints):
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
        lines_desc = describe_template_from_dict(
            {
                "lines": self.lines,
                "syllables_per_line": self.syllables_per_line,
                "syllable_constraints": self.get_syllable_constraints(),
            }
        )
        if self.rule_description:
            lines_desc += "\n" + self.rule_description
        return lines_desc

    def format_poem(self, poem: list[str]) -> str:
        """将无标点诗行格式化为可展示文本。

        子类可覆写以实现诗体专属格式（如标点、缩进、分段）。
        AI 生成的原始诗稿无标点、句间换行，本方法负责加上标点与排版。

        Args:
            poem: 无标点的诗行列表（每句一行）。

        Returns:
            格式化后的展示文本。
        """
        return "\n".join(poem)


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

#: 自定义模板编辑器支持的逐位约束方案：语言 -> (属性维度键, 可选值元组)。
#: 维度键即写入 attributes 的真实取值字段；空维度（""）表示该语言无语位约束，
#: 只能通过 validate_full 整体规则（押韵/行级条件）来限定。
_CUSTOM_SCHEMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "zh": ("tone", ("平", "仄")),
    "en": ("stress", ("light", "heavy")),
    "it": ("stress", ("light", "heavy")),
    "la": ("length", ("long", "short")),
    "fr": ("", ()),
}


def custom_template_schemes() -> dict[str, tuple[str, tuple[str, ...]]]:
    """返回自定义模板各语言的逐位约束方案（含受支持语言清单）。

    Returns:
        {"zh": ("tone", ("平", "仄")), ...}；键即受支持语言，
        值为 (属性维度键, 可选值元组)。
    """
    return dict(_CUSTOM_SCHEMES)


def template_helpers(language: str) -> tuple[str, ...]:
    """列出某语言模板模块中可复用的 ``_check_*`` 辅助函数名。

    用于自定义代码编辑器的提示：生成的模板会以 ``rules`` 别名导入对应
    语言模块，自定义代码可通过 ``rules.<函数名>`` 复用这些整体规则函数。

    Args:
        language: 语言代码（zh/en/it/fr/la）。

    Returns:
        按字母排序的辅助函数名元组；语言模块不存在时抛出 ModuleNotFoundError。
    """
    import importlib

    module = importlib.import_module(f"{__package__}.{language}")
    return tuple(sorted(name for name in dir(module) if name.startswith("_check_")))


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
