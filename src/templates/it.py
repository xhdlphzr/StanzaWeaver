# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""意大利语格律模板：三行体（Terza Rima）、八行体（Ottava Rima）、歌谣。

十一音节句（endecasillabo）的定义特征：每行第 10 个音节必须重读。
"""

from typing import ClassVar

from ..models.syllable import Syllable
from . import ConstraintTable, PoetryTemplate, register


def _check_tenth_syllable_stress(
    syllables: list[list[Syllable]],
    errors: list[str],
    indices: list[int] | None = None,
) -> None:
    """检查 11 音节句的第 10 音节须重读、第 11 音节须非重读。

    仅对传入（或默认全部）行中长度足够的行生效：10 音节及以上需第 10
    音节重读；11 音节及以上还需第 11 音节不可重读（避免 tronca 误判）。

    Args:
        syllables: 各行音节。
        errors: 错误列表（就地追加）。
        indices: 仅检查这些行号（0-based）；为 None 时检查全部行。
    """
    targets = indices if indices is not None else list(range(len(syllables)))
    for i in targets:
        syls = syllables[i]
        if len(syls) >= 10 and syls[9].attributes.get("stress") != "heavy":
            errors.append(f"第{i + 1}行第10音节应重读，实际未重读")
        if len(syls) >= 11 and syls[10].attributes.get("stress") == "heavy":
            errors.append(f"第{i + 1}行第11音节不应重读")


def _check_last_syllable_stress(
    syllables: list[list[Syllable]],
    errors: list[str],
    indices: list[int] | None = None,
) -> None:
    """检查指定行末音节必须重读（tronca 行尾）。

    Args:
        syllables: 各行音节。
        errors: 错误列表（就地追加）。
        indices: 仅检查这些行号（0-based）；为 None 时检查全部行。
    """
    targets = indices if indices is not None else list(range(len(syllables)))
    for i in targets:
        syls = syllables[i]
        if syls and syls[-1].attributes.get("stress") != "heavy":
            errors.append(f"第{i + 1}行末音节应重读，实际未重读")


def _check_rhyme_group(
    syllables: list[list[Syllable]], indices: list[int], label: str, errors: list[str]
) -> None:
    """检查一组行末音节同韵（韵腹+韵尾）。

    Args:
        syllables: 各行音节。
        indices: 参与该韵组的行号（0-based）。
        label: 韵组名。
        errors: 错误列表（就地追加）。
    """
    rhymes: list[tuple[int, str]] = []
    for idx in indices:
        if idx < len(syllables) and syllables[idx]:
            r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
            if r:
                rhymes.append((idx, r))
    if len(rhymes) >= 2:
        base = rhymes[0][1]
        for idx, r in rhymes[1:]:
            if r != base:
                errors.append(
                    f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'"
                )


class TerzaRimaTemplate(PoetryTemplate):
    """三行体：14 行十一音节句，链式循环押韵 ABA BCB CDC DED EE。"""

    name = "三行体"
    language = "it"
    lines = 14
    syllables_per_line: ClassVar[list[int]] = [11] * 14
    rule_description = (
        "格律规则：每行11音节（跨词元音连读 sinalefe 合并计数）；"
        "每行第10个音节必须重读（十一音节句定义特征）；"
        "韵式 ABA BCB CDC DED EE（链式循环押韵，换韵时与前韵不同部）。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。

        Returns:
            逐位音节约束表。
        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：第10音节重读 + 链式韵式。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
        _check_tenth_syllable_stress(syllables, errors)
        rhyme_groups = [
            ([0, 2], "ABA"),
            ([1, 3, 5], "BCB"),
            ([4, 6, 8], "CDC"),
            ([7, 9, 11], "DED"),
            ([10, 12, 13], "EE"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(syllables, indices, label, errors)
        return errors


class OttavaRimaTemplate(PoetryTemplate):
    """八行体：8 行十一音节句，韵式 ABABABCC。"""

    name = "八行体"
    language = "it"
    lines = 8
    syllables_per_line: ClassVar[list[int]] = [11] * 8
    rule_description = (
        "格律规则：每行11音节（跨词元音连读 sinalefe 合并计数）；"
        "每行第10个音节必须重读；"
        "韵式 ABABABCC（前6行交替韵，末两行对句韵 CC）。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。

        Returns:
            逐位音节约束表。
        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：第10音节重读 + ABABABCC 韵式。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
        _check_tenth_syllable_stress(syllables, errors)
        rhyme_groups = [
            ([0, 2, 4], "A"),
            ([1, 3, 5], "B"),
            ([6, 7], "CC"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(syllables, indices, label, errors)
        return errors


class CanzoneTemplate(PoetryTemplate):
    """歌谣：13 行（11/7 音节交错），奇数行末非重读、偶数行与末行重读，韵脚至多 4 个。"""

    name = "歌谣"
    language = "it"
    lines = 13
    syllables_per_line: ClassVar[list[int]] = [
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        11,
        7,
        7,
    ]
    rule_description = (
        "格律规则：奇数行（1、3、5、7、9、11）为11音节（endecasillabo femminile），"
        "第10音节重读、第11音节非重读；"
        "偶数行（2、4、6、8、10、12）与第13行为7音节（settenario femminile），末音节重读；"
        "全诗使用 A、B、C、D 四个韵脚，同一韵脚连续出现不得超过两次，末三行韵脚各不相同。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。

        Returns:
            逐位音节约束表。
        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：奇数行（11 音节）第 10 重读/第 11 非重读，偶数行与
        第 13 行（7 音节）末音节重读；韵脚 ≤4、连续同韵 ≤2、末三行各异。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
        # 奇数行（1,3,5,7,9,11）：11 音节，第 10 音节重读、第 11 不可重读
        _check_tenth_syllable_stress(syllables, errors, indices=[0, 2, 4, 6, 8, 10])
        # 偶数行（2,4,6,8,10,12）及第 13 行：7 音节，末音节重读
        _check_last_syllable_stress(syllables, errors, indices=[1, 3, 5, 7, 9, 11, 12])

        distinct: set[str] = set()
        for syls in syllables:
            if syls:
                r = syls[-1].nucleus + syls[-1].coda
                if r:
                    distinct.add(r)
        if len(distinct) > 4:
            errors.append(
                f"全诗韵脚数量应为4个以内，当前为{len(distinct)}个: {sorted(distinct)}"
            )

        prev = ""
        streak = 0
        for idx, syls in enumerate(syllables):
            r = syls[-1].nucleus + syls[-1].coda if syls else ""
            if r and r == prev:
                streak += 1
                if streak >= 2:
                    errors.append(
                        f"第{idx + 1}行与第{idx}行、第{idx - 1}行连续同一韵脚，超过两次"
                    )
                    streak = 0
            else:
                streak = 0
            prev = r

        tails: list[str] = []
        for idx in (10, 11, 12):
            if idx < len(syllables) and syllables[idx]:
                tails.append(syllables[idx][-1].nucleus + syllables[idx][-1].coda)
        if len(tails) == 3 and len(set(tails)) < 3:
            errors.append(f"末三行韵脚须各不相同，实际为 {tails}")

        return errors


def register_italian_templates() -> None:
    """注册全部意大利语模板。"""
    register("it_terza_rima", TerzaRimaTemplate())
    register("it_ottava_rima", OttavaRimaTemplate())
    register("it_canzone", CanzoneTemplate())
