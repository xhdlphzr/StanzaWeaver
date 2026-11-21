# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""可数据化的结构规则校验（供跨语言转化携带）.

近体诗（绝句/律诗）的规则原先只写在模板类的代码里：平仄相间/相对/相粘、
出句对句脚、三平尾、孤平、押平声韵。这些规则本质上只依赖“某个属性值”
（汉语为平/仄，英语可映射为重/轻……），因此可以数据化为一份
``structural_rules`` 描述，由本模块统一校验：

    {
        "kind": "jinti",
        "attribute": "tone",          # 音节属性键
        "level_value": "平",           # 相当于“平”的属性值
        "oblique_value": "仄",         # 相当于“仄”的属性值
        "positions": [1, 3],           # 需要相间/相对/相粘的固定位（0-based）
        "rhyme_lines": [1, 3],         # 必须押韵的行号（0-based）
        "optional_first_rhyme": True,  # 首句若为 level_value 则须一并押韵
        "forbid_sanpingwei": True,     # 禁止三平尾
        "forbid_guping": True,          # 禁止孤平
    }

跨语言转化时，只需把 ``attribute``/``level_value``/``oblique_value`` 按映射
换成目标语言的属性与值，其余字段原样复制，规则即可在新语言中生效。
"""

from typing import Any

from ..models.syllable import Syllable
from .rhyme import rhyme_keys

#: 结构规则允许的 kind（目前只有近体诗）。
STRUCTURAL_KINDS: tuple[str, ...] = ("jinti",)

#: 结构规则字典的合法键。
STRUCTURAL_KEYS: tuple[str, ...] = (
    "kind",
    "attribute",
    "level_value",
    "oblique_value",
    "positions",
    "rhyme_lines",
    "optional_first_rhyme",
    "forbid_sanpingwei",
    "forbid_guping",
)


def _as_int_list(value: Any) -> list[int] | None:
    """把任意值转为非负整数列表.

    Args:
        value: 原始值。

    Returns:
        整数列表；非法时返回 None。

    """
    if not isinstance(value, (list, tuple)):
        return None
    result: list[int] = []
    for item in value:
        try:
            number = int(item)
        except TypeError, ValueError:
            return None
        if number < 0:
            return None
        result.append(number)
    return result


def normalize_structural_rules(
    raw: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """校验并规整结构规则数据（供创建模板接口与 AI 草稿使用）.

    Args:
        raw: 原始结构规则（可为 None）。

    Returns:
        (规整后的规则或 None, 错误信息)；合法时错误信息为 None。

    """
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, "structural_rules 必须是对象"
    kind = str(raw.get("kind", "")).strip()
    if kind not in STRUCTURAL_KINDS:
        return None, f"未知的结构规则类型 {kind!r}"
    attribute = str(raw.get("attribute", "")).strip()
    level_value = str(raw.get("level_value", "")).strip()
    oblique_value = str(raw.get("oblique_value", "")).strip()
    if not attribute or not level_value or not oblique_value:
        return None, "结构规则缺少 attribute/level_value/oblique_value"
    positions = _as_int_list(raw.get("positions"))
    rhyme_lines = _as_int_list(raw.get("rhyme_lines"))
    if not positions or not rhyme_lines:
        return None, "结构规则缺少 positions/rhyme_lines"
    return (
        {
            "kind": kind,
            "attribute": attribute,
            "level_value": level_value,
            "oblique_value": oblique_value,
            "positions": positions,
            "rhyme_lines": rhyme_lines,
            "optional_first_rhyme": bool(raw.get("optional_first_rhyme", False)),
            "forbid_sanpingwei": bool(raw.get("forbid_sanpingwei", False)),
            "forbid_guping": bool(raw.get("forbid_guping", False)),
        },
        None,
    )


def _value_at(syllables: list[Syllable], position: int, attribute: str) -> str:
    """取某行固定位的属性值.

    Args:
        syllables: 一行音节。
        position: 位置（0-based）。
        attribute: 属性键。

    Returns:
        属性值；越界或未知时返回空串。

    """
    if position < 0 or position >= len(syllables):
        return ""
    return str(syllables[position].attributes.get(attribute, "") or "")


def _last_value(syllables: list[Syllable], attribute: str) -> str:
    """取某行末音节的属性值.

    Args:
        syllables: 一行音节。
        attribute: 属性键。

    Returns:
        属性值；空行返回空串。

    """
    if not syllables:
        return ""
    return str(syllables[-1].attributes.get(attribute, "") or "")


def check_jinti_rules(
    language: str,
    poem: list[str],
    syllables: list[list[Syllable]],
    rules: dict[str, Any],
) -> list[str]:
    """按数据化的近体诗结构规则校验整首诗.

    Args:
        language: 语言代码（决定押韵 key 的计算口径）。
        poem: 诗行文本。
        syllables: 每行音节列表。
        rules: 规整后的结构规则（见模块文档）。

    Returns:
        错误信息列表；全部通过时返回空列表。

    """
    errors: list[str] = []
    if not syllables or len(syllables) < 2:
        return errors
    attribute = str(rules.get("attribute", ""))
    level = str(rules.get("level_value", ""))
    oblique = str(rules.get("oblique_value", ""))
    positions = [int(p) for p in rules.get("positions", [])]
    rhyme_lines = [int(p) for p in rules.get("rhyme_lines", [])]
    forbid_sanpingwei = bool(rules.get("forbid_sanpingwei", False))
    forbid_guping = bool(rules.get("forbid_guping", False))
    optional_first_rhyme = bool(rules.get("optional_first_rhyme", False))

    fixed_positions = [
        position
        for position in positions
        if not syllables[0] or position < len(syllables[0])
    ]

    for i, line_syllables in enumerate(syllables):
        if not line_syllables:
            continue
        last_value = _last_value(line_syllables, attribute)
        if forbid_sanpingwei and len(line_syllables) >= 3:
            tail = [
                _value_at(line_syllables, len(line_syllables) - k, attribute)
                for k in (3, 2, 1)
            ]
            if level and tail == [level, level, level]:
                errors.append(f"第{i + 1}行三平尾: 末三音节均为'{level}'")
        if forbid_guping and level and last_value == level:
            level_count = sum(
                1
                for syl in line_syllables
                if str(syl.attributes.get(attribute, "") or "") == level
            )
            if level_count == 1:
                errors.append(f"第{i + 1}行孤平: 平脚句全句仅一个'{level}'音节")

    prev_inner: list[str] | None = None
    for i in range(0, len(syllables) - 1, 2):
        outer = [
            _value_at(syllables[i], position, attribute) for position in fixed_positions
        ]
        inner = [
            _value_at(syllables[i + 1], position, attribute)
            for position in fixed_positions
        ]
        if i >= 2 and syllables[i] and _last_value(syllables[i], attribute) == level:
            errors.append(f"第{i + 1}行为出句，尾音节应为'{oblique}'，实际为'{level}'")
        if syllables[i + 1] and _last_value(syllables[i + 1], attribute) == oblique:
            errors.append(f"第{i + 2}行为对句，尾音节应为'{level}'，实际为'{oblique}'")

        for j in range(len(fixed_positions) - 1):
            for index, values in ((i, outer), (i + 1, inner)):
                first = values[j] if j < len(values) else ""
                second = values[j + 1] if j + 1 < len(values) else ""
                if first and second and first == second:
                    errors.append(
                        f"第{index + 1}行第{fixed_positions[j] + 1}音节与"
                        f"第{fixed_positions[j + 1] + 1}音节平仄应相间，实际均为'{first}'"
                    )
        for j, (first, second) in enumerate(zip(outer, inner)):
            if first and second and first == second:
                errors.append(
                    f"第{i + 1}行与第{i + 2}行应相对: 第{fixed_positions[j] + 1}"
                    f"音节平仄应相反，实际均为'{first}'"
                )
        if prev_inner is not None:
            for j, (first, second) in enumerate(zip(prev_inner, outer)):
                if first and second and first != second:
                    errors.append(
                        f"第{i + 1}行应与第{i}行相粘: 第{fixed_positions[j] + 1}"
                        f"音节平仄应相同，实际'{first}'与'{second}'"
                    )
        prev_inner = inner

    rhyme_keys_list: list[tuple[int, set[str]]] = []
    for index in rhyme_lines:
        if index >= len(syllables) or not syllables[index]:
            continue
        last_value = _last_value(syllables[index], attribute)
        if level and last_value != level:
            errors.append(
                f"第{index + 1}行韵脚应为'{level}'，实际为'{last_value or '未知'}'"
            )
        keys = rhyme_keys(language, poem[index], syllables[index])
        if keys is not None:
            rhyme_keys_list.append((index, keys))
    if (
        optional_first_rhyme
        and syllables
        and syllables[0]
        and level
        and _last_value(syllables[0], attribute) == level
    ):
        keys = rhyme_keys(language, poem[0], syllables[0])
        if keys is not None:
            rhyme_keys_list.insert(0, (0, keys))
    if len(rhyme_keys_list) >= 2:
        common = set(rhyme_keys_list[0][1])
        for _, keys in rhyme_keys_list[1:]:
            common &= keys
        if not common:
            first_index, first_keys = rhyme_keys_list[0]
            last_index, last_keys = rhyme_keys_list[-1]
            errors.append(
                f"押韵不匹配: 第{first_index + 1}行韵脚为"
                f"'{'/'.join(sorted(key.split(':', 1)[-1] for key in first_keys))}'，"
                f"第{last_index + 1}行韵脚为"
                f"'{'/'.join(sorted(key.split(':', 1)[-1] for key in last_keys))}'，不押韵"
            )
    return errors
