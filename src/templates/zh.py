# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""中文格律模板：五言绝句、七言绝句、五言律诗、七言律诗、相见欢。

实现近体诗/词牌的符号层规则：
- 平仄骨架：每句 2/4(6) 位相间、联内相对、联间相粘、出句仄脚/对句平脚；
- 押韵：偶数行平声韵（一韵到底，依《中华通韵》16 韵部），首句可入韵，词牌按谱换韵；
- 禁忌：三平尾、孤平（三仄尾不计入禁忌）。
"""

from typing import Any, ClassVar

from ..models.syllable import Syllable
from . import ConstraintTable, PoetryTemplate, register


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


def _tone(t: str) -> dict[str, Any]:
    """构造仅限声调的约束。

    Args:
        t: "平" 或 "仄"。

    Returns:
        约束字典。
    """
    return _make_syl(attributes={"tone": t})


_FREE: dict[str, Any] = _make_syl()


def _check_sanpingwei(syllables: list[Syllable]) -> list[str]:
    """检查三平尾（末三字全平）。

    Args:
        syllables: 一行音节。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    if len(syllables) >= 3:
        last3 = [s.attributes.get("tone", "") for s in syllables[-3:]]
        if last3 == ["平", "平", "平"]:
            errors.append("三平尾: 末三字皆为平声，不合律")
    return errors


def _check_guping(syllables: list[Syllable]) -> list[str]:
    """检查孤平：平脚句（尾字平声）全句仅一个平声字（即韵脚）即为孤平。

    孤平为近体诗大忌：平声收尾之句若除去韵脚外再无第二个平声字，则孤平失律。
    仄脚句（尾字仄声）不检孤平。

    Args:
        syllables: 一行音节。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    if not syllables:
        return errors
    if syllables[-1].attributes.get("tone", "") != "平":
        return errors
    ping_count = sum(1 for s in syllables if s.attributes.get("tone", "") == "平")
    if ping_count == 1:
        errors.append("孤平: 平脚句全句仅一平声（韵脚），孤平失律")
    return errors


def _check_alternation(syllables: list[Syllable], even_pattern: list[str]) -> list[str]:
    """二四六分明检查：偶数位必须与给定平仄模式一致。

    Args:
        syllables: 一行音节。
        even_pattern: 偶数位期望平仄列表。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    n = len(syllables)
    for pos_idx, expected in enumerate(even_pattern):
        actual_pos = pos_idx * 2 + 1
        if actual_pos < n:
            actual_tone = syllables[actual_pos].attributes.get("tone", "")
            if actual_tone and actual_tone != expected:
                errors.append(
                    f"第{actual_pos + 1}字应为{expected}声（二四六分明），实际为{actual_tone}"
                )
    return errors


# 《中华通韵》16 韵部归并（以韵腹+韵尾为键，ü 在 pypinyin 中记为 v）。
# 关键修正（相对旧十三辙）：齐齿 "i/ü/er" 与 "u" 不同部；舌尖元音 -i 单列 "支" 部。
_TONGYUN: dict[str, str] = {
    "a": "麻",
    "ia": "麻",
    "ua": "麻",
    "o": "波",
    "e": "波",
    "uo": "波",
    "ie": "皆",
    "üe": "皆",
    "ve": "皆",
    "ai": "开",
    "uai": "开",
    "ei": "微",
    "ui": "微",
    "ao": "豪",
    "iao": "豪",
    "ou": "尤",
    "iu": "尤",
    "an": "寒",
    "ian": "寒",
    "uan": "寒",
    "üan": "寒",
    "van": "寒",
    "en": "文",
    "in": "文",
    "un": "文",
    "ün": "文",
    "vn": "文",
    "ang": "唐",
    "iang": "唐",
    "uang": "唐",
    "eng": "庚",
    "ing": "庚",
    "ueng": "庚",
    "ong": "庚",
    "iong": "庚",
    "i": "齐",
    "er": "齐",
    "ü": "齐",
    "v": "齐",
    "u": "姑",
}

# 舌尖元音（知/吃/诗/日…）的声母：其韵母 -i 归入「支」部而非「齐」部。
_APICAL_ONSETS: frozenset[str] = frozenset({"z", "c", "s", "zh", "ch", "sh", "r"})


def _rhyme_key(syl: Syllable) -> str:
    """生成韵脚 key：按《中华通韵》归并韵腹+韵尾。

    取音节的韵腹+韵尾（已去除声调数字）查韵部表。特别地：当韵母为 "i"
    且声母属舌尖音 z/c/s/zh/ch/sh/r 时，归「支」部；否则 "i/ü/er" 归「齐」部，
    "u" 归「姑」部——齐与姑不同部，故 "i" 与 "u" 不押韵。

    Args:
        syl: 韵脚音节。

    Returns:
        韵部名（如 "庚"、"麻"），未知韵母返回原串或 "?"。
    """
    nucleus = syl.nucleus or ""
    coda = syl.coda or ""
    raw = nucleus + coda
    if raw == "i" and syl.onset in _APICAL_ONSETS:
        return "支"
    if raw in _TONGYUN:
        return _TONGYUN[raw]
    return raw or "?"


def _check_rhyme(
    syllables_list: list[list[Syllable]],
    rhyme_lines: list[int],
    description: str = "押韵",
) -> list[str]:
    """检查指定行韵脚（末音节韵腹+韵尾）是否同韵。

    Args:
        syllables_list: 各行音节。
        rhyme_lines: 参与押韵的行号（0-based）。
        description: 错误描述前缀。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    rhyme_keys: list[tuple[int, str]] = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            rhyme_keys.append((line_idx, _rhyme_key(last)))
    if len(rhyme_keys) < 2:
        return errors
    base_idx, base_rhyme = rhyme_keys[0]
    for line_idx, rhyme in rhyme_keys[1:]:
        if rhyme and rhyme != base_rhyme:
            errors.append(
                f"{description}: 第{base_idx + 1}行韵脚为'{base_rhyme}'，第{line_idx + 1}行韵脚为'{rhyme}'，不押韵"
            )
    return errors


def _check_jinti_rhyme(
    syllables_list: list[list[Syllable]],
    rhyme_lines: list[int],
    description: str = "押韵",
) -> list[str]:
    """近体诗押韵检查：偶数行必须押平声韵；首句尾字为平声时一并入韵。

    Args:
        syllables_list: 各行音节。
        rhyme_lines: 偶数行号（0-based）。
        description: 错误描述前缀。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    keys: list[tuple[int, str]] = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            if last.attributes.get("tone", "") != "平":
                errors.append(
                    f"第{line_idx + 1}行韵脚应为平声字，实际为'{last.attributes.get('tone') or '未知'}'"
                )
            keys.append((line_idx, _rhyme_key(last)))
    first = syllables_list[0][-1] if syllables_list and syllables_list[0] else None
    if first is not None and first.attributes.get("tone") == "平":
        keys.insert(0, (0, _rhyme_key(first)))
    if len(keys) < 2:
        return errors
    base_idx, base_rhyme = keys[0]
    for line_idx, rhyme in keys[1:]:
        if rhyme and rhyme != base_rhyme:
            errors.append(
                f"{description}: 第{base_idx + 1}行韵脚为'{base_rhyme}'，第{line_idx + 1}行韵脚为'{rhyme}'，不押韵"
            )
    return errors


def _check_jinti_structure(
    syllables_list: list[list[Syllable]],
) -> list[str]:
    """近体诗句式结构检查：每句 2/4(6) 位平仄相间、联内相对、联间相粘。

    出句（第 3 行起奇数行）须仄脚，对句（偶数行）须平脚；tone 未知跳过。

    Args:
        syllables_list: 各行音节。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    if len(syllables_list) < 2:
        return errors
    first_len = len(syllables_list[0])
    positions = [1, 3] if first_len <= 5 else [1, 3, 5]

    def line_tones(idx: int) -> list[str]:
        """取一行的固定位平仄。

        Args:
            idx: 行号。

        Returns:
            固定位平仄列表（未知项为空串）。
        """
        syls = syllables_list[idx]
        return [syls[p].attributes.get("tone", "") for p in positions if p < len(syls)]

    prev_couplet_in: list[str] | None = None
    for i in range(0, len(syllables_list) - 1, 2):
        out = line_tones(i)
        in_ = line_tones(i + 1)

        # 出句(第3行起奇数行)仄脚；首句例外(可押韵平尾可仄尾)
        if i >= 2 and syllables_list[i]:
            last_tone = syllables_list[i][-1].attributes.get("tone", "")
            if last_tone == "平":
                errors.append(f"第{i + 1}行为出句，尾字应为仄声，实际为平")
        # 对句(偶数行)平脚
        if syllables_list[i + 1]:
            last_tone = syllables_list[i + 1][-1].attributes.get("tone", "")
            if last_tone == "仄":
                errors.append(f"第{i + 2}行为对句，尾字应为平声，实际为仄")

        # 每句 2/4(6) 位平仄相间
        for j in range(len(positions) - 1):
            for idx, tones in ((i, out), (i + 1, in_)):
                a = tones[j] if j < len(tones) else ""
                b = tones[j + 1] if j + 1 < len(tones) else ""
                if a and b and a == b:
                    errors.append(
                        f"第{idx + 1}行第{positions[j] + 1}字与第{positions[j + 1] + 1}字平仄应相间，实际均为'{a}'"
                    )

        # 联内相对
        for j, (a, b) in enumerate(zip(out, in_)):
            if a and b and a == b:
                errors.append(
                    f"第{i + 1}行与第{i + 2}行应相对: 第{positions[j] + 1}字平仄应相反，实际均为'{a}'"
                )

        # 联间相粘
        if prev_couplet_in is not None:
            for j, (a, b) in enumerate(zip(prev_couplet_in, out)):
                if a and b and a != b:
                    errors.append(
                        f"第{i + 1}行应与第{i}行相粘: 第{positions[j] + 1}字平仄应相同，实际'{a}'与'{b}'"
                    )

        prev_couplet_in = in_
    return errors


def _check_lv_alternation(
    syllables: list[Syllable], line_idx: int, constraints: list[list[dict[str, Any]]]
) -> list[str]:
    """律诗二四六分明检查（按约束表偶数位期望）。

    Args:
        syllables: 一行音节。
        line_idx: 行号。
        constraints: 逐位约束表。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    if line_idx < len(constraints) and len(syllables) >= 3:
        even_pattern: list[str] = []
        for pos in range(1, len(syllables), 2):
            if pos < len(constraints[line_idx]):
                expected = (
                    constraints[line_idx][pos].get("attributes", {}).get("tone", "")
                )
                if expected:
                    even_pattern.append(expected)
        if even_pattern:
            errors.extend(_check_alternation(syllables, even_pattern))
    return errors


class WujueTemplate(PoetryTemplate):
    """五言绝句：4 行 5 字，二四字定平仄，偶句平声韵。"""

    name = "五言绝句"
    language = "zh"
    lines = 4
    syllables_per_line: ClassVar[list[int]] = [5, 5, 5, 5]
    rule_description = (
        "格律规则：每句第2、4字平仄相间；每联上下句第2、4字平仄相对；"
        "下一联首句与上一联对句第2、4字平仄相粘；"
        "偶数句押平声韵，首句尾字可押韵(平)可不押韵(仄)；忌三平尾、孤平。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位固定约束（一三不论）。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整规则检查：三平尾/孤平/结构/押韵（三仄尾不计入禁忌）。"""
        errors: list[str] = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class QijueTemplate(PoetryTemplate):
    """七言绝句：4 行 7 字，二四六字定平仄，偶句平声韵。"""

    name = "七言绝句"
    language = "zh"
    lines = 4
    syllables_per_line: ClassVar[list[int]] = [7, 7, 7, 7]
    rule_description = (
        "格律规则：每句第2、4、6字平仄相间；每联上下句第2、4、6字平仄相对；"
        "下一联首句与上一联对句第2、4、6字平仄相粘；"
        "偶数句押平声韵，首句尾字可押韵(平)可不押韵(仄)；忌三平尾、孤平。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位固定约束（一三五不论）。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整规则检查：三平尾/孤平/结构/押韵（三仄尾不计入禁忌）。"""
        errors: list[str] = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class WulvTemplate(PoetryTemplate):
    """五言律诗：8 行 5 字，四联，偶句平声韵（对仗由检查 AI 负责）。"""

    name = "五言律诗"
    language = "zh"
    lines = 8
    syllables_per_line: ClassVar[list[int]] = [5] * 8
    rule_description = WujueTemplate.rule_description

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位固定约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整规则检查：三平尾/孤平/结构/押韵（三仄尾不计入禁忌）。"""
        errors: list[str] = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class QilvTemplate(PoetryTemplate):
    """七言律诗：8 行 7 字，四联，偶句平声韵（对仗由检查 AI 负责）。"""

    name = "七言律诗"
    language = "zh"
    lines = 8
    syllables_per_line: ClassVar[list[int]] = [7] * 8
    rule_description = QijueTemplate.rule_description

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位固定约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整规则检查：三平尾/孤平/结构/押韵（三仄尾不计入禁忌）。"""
        errors: list[str] = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class XiangjianhuanTemplate(PoetryTemplate):
    """相见欢（双调三十六字）：上阕三平韵，下阕先两仄韵换韵再转回平韵。"""

    name = "相见欢"
    language = "zh"
    lines = 7
    syllables_per_line: ClassVar[list[int]] = [6, 3, 9, 3, 3, 3, 9]
    rule_description = (
        "格律规则：上阕3句三平韵（中平中仄平平/仄平平/中仄中平平仄仄平平）；"
        "下阕4句先两仄韵（中中仄/中平仄）换韵、再转回平韵（仄平平/中仄中平平仄仄平平），"
        "下阕平韵须与上阕同部；上下阕末句末三字不宜全平。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """词牌固定平仄谱（"中"=自由）。"""
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _p, _f, _z, _p, _p],
            [_z, _p, _p],
            [_f, _z, _f, _p, _f, _z, _z, _p, _p],
            [_f, _f, _z],
            [_f, _p, _z],
            [_z, _p, _p],
            [_f, _z, _f, _p, _f, _z, _z, _p, _p],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """押韵检查：上阕三平韵、下阕仄韵换韵、平韵转回且须同部。

        另提示上下阕末句（第 3、7 行）末三字全平宜规避（非铁律）。
        """
        errors: list[str] = []
        for line_idx in (2, 6):
            if line_idx < len(syllables) and syllables[line_idx]:
                last3 = [s.attributes.get("tone", "") for s in syllables[line_idx][-3:]]
                if last3 == ["平", "平", "平"]:
                    errors.append(f"第{line_idx + 1}行末三字全平，宜规避")
        errors.extend(_check_rhyme(syllables, [0, 1, 2], "押韵(上阕·平韵)"))
        errors.extend(_check_rhyme(syllables, [3, 4], "押韵(下阕·仄韵·换韵)"))
        errors.extend(_check_rhyme(syllables, [5, 6], "押韵(下阕·平韵·换回)"))

        # 下阕平韵应转回上阕平声韵部；下阕仄韵须与平韵不同部（换韵）
        def tail(idx: int) -> str:
            """取指定行的韵脚 key。

            Args:
                idx: 行号。

            Returns:
                韵脚串；无音节时返回空串。
            """
            if idx < len(syllables) and syllables[idx]:
                return _rhyme_key(syllables[idx][-1])
            return ""

        upper = tail(0)
        lower_ping = tail(5)
        lower_ze = tail(3)
        if upper and lower_ping and upper != lower_ping:
            errors.append(
                f"下阕平韵应转回上阕平声韵部: 上阕'{upper}'，下阕'{lower_ping}'"
            )
        if upper and lower_ze and lower_ze == upper:
            errors.append(f"下阕仄韵应与平韵不同部（换韵）: 均为'{lower_ze}'")
        return errors


def register_chinese_templates() -> None:
    """注册全部中文模板。"""
    register("zh_wujue", WujueTemplate())
    register("zh_qijue", QijueTemplate())
    register("zh_wulv", WulvTemplate())
    register("zh_qilv", QilvTemplate())
    register("zh_xiangjianhuan", XiangjianhuanTemplate())
