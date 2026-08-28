"""意大利语格律模板：三行体（Terza Rima）、八行体（Ottava Rima）、歌谣。

十一音节句（endecasillabo）的定义特征：每行第 10 个音节必须重读。
"""

from typing import ClassVar

from ..models.syllable import Syllable
from . import ConstraintTable, PoetryTemplate, register


def _check_tenth_syllable_stress(
    syllables: list[list[Syllable]], errors: list[str]
) -> None:
    """检查每行第 10 个音节（0-based 9）必须重读。

    Args:
        syllables: 各行音节。
        errors: 错误列表（就地追加）。
    """
    for i, syls in enumerate(syllables):
        if len(syls) >= 10 and syls[9].attributes.get("stress") != "heavy":
            errors.append(f"第{i + 1}行第10音节应重读，实际未重读")


def _check_last_syllable_stress(
    syllables: list[list[Syllable]], errors: list[str]
) -> None:
    """检查每行末音节必须重读（tronca 行尾）。

    Args:
        syllables: 各行音节。
        errors: 错误列表（就地追加）。
    """
    for i, syls in enumerate(syllables):
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
        """无逐位约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：第10音节重读 + 链式韵式。"""
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
        """无逐位约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：第10音节重读 + ABABABCC 韵式。"""
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
    """歌谣：13 行（11/7 音节交错），末音节重读，韵脚至多 4 个。"""

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
        "格律规则：奇数行（1、3、5、7、9、11）为11音节，"
        "偶数行（2、4、6、8、10、12）为7音节，第13行为7音节；"
        "每行末音节必须重读（行尾须用 tronca 词，如 amor、virtù、perché）；"
        "全诗使用 A、B、C、D 四个韵脚，同一韵脚连续出现不得超过两次，末三行韵脚各不相同。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：末音节重读、韵脚 ≤4、连续同韵 ≤2、末三行各异。"""
        errors: list[str] = []
        _check_last_syllable_stress(syllables, errors)

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
