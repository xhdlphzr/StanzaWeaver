# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from . import PoetryTemplate, register


def _check_tenth_syllable_stress(syllables, errors) -> None:
    """每行第10个音节（0-based 9）必须重读 —— 十一音节句（endecasillabo）的定义特征。"""
    for i, syls in enumerate(syllables):
        if len(syls) >= 10 and syls[9].attributes.get("stress") != "heavy":
            errors.append(f"第{i + 1}行第10音节应重读，实际未重读")


def _check_last_syllable_stress(syllables, errors) -> None:
    for i, syls in enumerate(syllables):
        if syls and syls[-1].attributes.get("stress") != "heavy":
            errors.append(f"第{i + 1}行末音节应重读，实际未重读")


def _check_rhyme_group(syllables, indices, label, errors) -> None:
    rhymes = []
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
    name = "三行体"
    language = "it"
    lines = 14
    syllables_per_line = [11] * 14
    rule_description = (
        "格律规则：每行11音节（跨词元音连读 sinalefe 合并计数）；"
        "每行第10个音节必须重读（十一音节句定义特征）；"
        "韵式 ABA BCB CDC DED EE（链式循环押韵，换韵时与前韵不同部）。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
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
    name = "八行体"
    language = "it"
    lines = 8
    syllables_per_line = [11] * 8
    rule_description = (
        "格律规则：每行11音节（跨词元音连读 sinalefe 合并计数）；"
        "每行第10个音节必须重读；"
        "韵式 ABABABCC（前6行交替韵，末两行对句韵 CC）。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
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
    name = "歌谣"
    language = "it"
    lines = 13
    syllables_per_line = [11, 11, 7, 7, 11, 11, 7, 11, 7, 11, 11, 7, 11]
    rule_description = (
        "格律规则：奇数行（1、3、5、7、9、11）为11音节，"
        "偶数行（2、4、6、8、10、12）为7音节，第13行为7音节；"
        "每行末音节必须重读（行尾须用 tronca 词，如 amor、virtù、perché）；"
        "全诗使用 A、B、C、D 四个韵脚，同一韵脚连续出现不得超过两次，末三行韵脚各不相同。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        _check_last_syllable_stress(syllables, errors)

        # 全诗韵脚至多 4 个
        distinct = set()
        for syls in syllables:
            if syls:
                r = syls[-1].nucleus + syls[-1].coda
                if r:
                    distinct.add(r)
        if len(distinct) > 4:
            errors.append(
                f"全诗韵脚数量应为4个以内，当前为{len(distinct)}个: {sorted(distinct)}"
            )

        # 段内同一韵脚不得连续出现超过两次
        prev = None
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

        # 末三行韵脚须各不相同
        tails = []
        for idx in (10, 11, 12):
            if idx < len(syllables) and syllables[idx]:
                tails.append(syllables[idx][-1].nucleus + syllables[idx][-1].coda)
        if len(tails) == 3 and len(set(tails)) < 3:
            errors.append(f"末三行韵脚须各不相同，实际为 {tails}")

        return errors


def register_italian_templates():
    register("it_terza_rima", TerzaRimaTemplate())
    register("it_ottava_rima", OttavaRimaTemplate())
    register("it_canzone", CanzoneTemplate())
