# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from . import PoetryTemplate, register
from ..models.syllable import Syllable


def _make_syl(**kwargs) -> dict:
    attrs = kwargs.pop("attributes", {})
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


def _tone(t: str) -> dict:
    return _make_syl(attributes={"tone": t})


_FREE = _make_syl()


def _check_sanpingwei(syllables: list[Syllable]) -> list[str]:
    errors = []
    if len(syllables) >= 3:
        last3 = [s.attributes.get("tone", "") for s in syllables[-3:]]
        if last3 == ["平", "平", "平"]:
            errors.append("三平尾: 末三字皆为平声，不合律")
    return errors


def _check_sanzewei(syllables: list[Syllable]) -> list[str]:
    errors = []
    if len(syllables) >= 3:
        last3 = [s.attributes.get("tone", "") for s in syllables[-3:]]
        if last3 == ["仄", "仄", "仄"]:
            errors.append("三仄尾: 末三字皆为仄声，不合律")
    return errors


def _check_guping(syllables: list[Syllable]) -> list[str]:
    errors = []
    n = len(syllables)
    if n < 3:
        return errors
    for i in range(1, n - 1):
        prev = syllables[i - 1].attributes.get("tone", "")
        curr = syllables[i].attributes.get("tone", "")
        nxt = syllables[i + 1].attributes.get("tone", "")
        if prev == "仄" and curr == "平" and nxt == "仄":
            if i == n - 2:
                continue
            errors.append(f"孤平: 第{i + 1}字为孤立的平声（前后皆为仄声）")
    return errors


def _check_alternation(syllables: list[Syllable], even_pattern: list[str]) -> list[str]:
    errors = []
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


# 拼音省写映射: iou→iu, uei→ui, uen→un, üen→vn，押韵取省写前的韵腹+韵尾
_RHYME_MEDIAL_MAP = {
    "iu": "ou",
    "ui": "ei",
    "un": "en",
    "vn": "en",
    "ün": "en",
}


def _rhyme_key(syl: Syllable) -> str:
    """韵脚 key：忽略介音（韵头），只取韵腹+韵尾，如 ang/uang/iang 视为同韵。"""
    nucleus = syl.nucleus
    if len(nucleus) > 1 and nucleus[0] in ("i", "u", "ü", "v"):
        if nucleus in _RHYME_MEDIAL_MAP:
            return _RHYME_MEDIAL_MAP[nucleus] + syl.coda
        nucleus = nucleus[1:]
    if nucleus in _RHYME_MEDIAL_MAP:
        return _RHYME_MEDIAL_MAP[nucleus] + syl.coda
    return nucleus + syl.coda


def _check_rhyme(
    syllables_list: list[list[Syllable]],
    rhyme_lines: list[int],
    description: str = "押韵",
) -> list[str]:
    """Check that specified lines share the same rhyme (nucleus + coda of last syllable)."""
    errors = []
    rhyme_keys = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            rhyme_keys.append((line_idx, _rhyme_key(last)))
    if len(rhyme_keys) < 2:
        return errors
    base_idx, base_rhyme = rhyme_keys[0]
    if not base_rhyme:
        return errors
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
    """近体诗押韵检查：偶数行必须押平声韵；首句尾字为平声时一并入韵（首句入韵式），
    为仄声时不入韵（首句不入韵式）。"""
    errors = []
    keys = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            if last.attributes.get("tone", "") != "平":
                errors.append(f"第{line_idx + 1}行韵脚应为平声字，实际为'{last.attributes.get('tone') or '未知'}'")
            keys.append((line_idx, _rhyme_key(last)))
    first = syllables_list[0][-1] if syllables_list and syllables_list[0] else None
    if first is not None and first.attributes.get("tone") == "平":
        keys.insert(0, (0, _rhyme_key(first)))
    if len(keys) < 2:
        return errors
    base_idx, base_rhyme = keys[0]
    if not base_rhyme:
        return errors
    for line_idx, rhyme in keys[1:]:
        if rhyme and rhyme != base_rhyme:
            errors.append(
                f"{description}: 第{base_idx + 1}行韵脚为'{base_rhyme}'，第{line_idx + 1}行韵脚为'{rhyme}'，不押韵"
            )
    return errors


def _check_jinti_structure(
    syllables_list: list[list[Syllable]],
) -> list[str]:
    """近体诗句式结构检查：每句第2/4(6)字平仄相间（四种基本句式特征）、
    联内相对（出句与对句在 2/4(6) 位平仄相反）、联间相粘（下一联出句与
    上一联对句在 2/4(6) 位平仄相同）。tone 未知的字跳过不判。"""
    errors = []
    if len(syllables_list) < 2:
        return errors
    first_len = len(syllables_list[0])
    positions = [1, 3] if first_len <= 5 else [1, 3, 5]

    def line_tones(idx: int) -> list[str]:
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
    syllables: list[Syllable], line_idx: int, constraints: list[list[dict]]
) -> list[str]:
    errors = []
    if line_idx < len(constraints) and len(syllables) >= 3:
        even_pattern = []
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
    name = "五言绝句"
    language = "zh"
    lines = 4
    syllables_per_line = [5, 5, 5, 5]
    rule_description = (
        "格律规则：每句第2、4字平仄相间；每联上下句第2、4字平仄相对；"
        "下一联首句与上一联对句第2、4字平仄相粘；"
        "偶数句押平声韵，首句尾字可押韵(平)可不押韵(仄)；忌三平尾、三仄尾、孤平。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_sanzewei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class QijueTemplate(PoetryTemplate):
    name = "七言绝句"
    language = "zh"
    lines = 4
    syllables_per_line = [7, 7, 7, 7]
    rule_description = (
        "格律规则：每句第2、4、6字平仄相间；每联上下句第2、4、6字平仄相对；"
        "下一联首句与上一联对句第2、4、6字平仄相粘；"
        "偶数句押平声韵，首句尾字可押韵(平)可不押韵(仄)；忌三平尾、三仄尾、孤平。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_sanzewei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class WulvTemplate(PoetryTemplate):
    name = "五言律诗"
    language = "zh"
    lines = 8
    syllables_per_line = [5] * 8
    rule_description = WujueTemplate.rule_description

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_sanzewei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class QilvTemplate(PoetryTemplate):
    name = "七言律诗"
    language = "zh"
    lines = 8
    syllables_per_line = [7] * 8
    rule_description = QijueTemplate.rule_description

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_sanzewei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_jinti_structure(syllables))
        errors.extend(_check_jinti_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class XiangjianhuanTemplate(PoetryTemplate):
    name = "相见欢"
    language = "zh"
    lines = 7
    syllables_per_line = [6, 3, 9, 3, 3, 3, 9]

    def get_syllable_constraints(self):
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

    def validate_full(self, poem, syllables):
        errors = []
        # 禁忌: 上下阕末句（第3、第7行）末三字不宜全平（非铁律，提示但不断然否决）
        for line_idx in (2, 6):
            if line_idx < len(syllables) and syllables[line_idx]:
                last3 = [s.attributes.get("tone", "") for s in syllables[line_idx][-3:]]
                if last3 == ["平", "平", "平"]:
                    errors.append(f"第{line_idx + 1}行末三字全平，宜规避")
        errors.extend(_check_rhyme(syllables, [0, 1, 2], "押韵(上阕·平韵)"))
        errors.extend(_check_rhyme(syllables, [3, 4], "押韵(下阕·仄韵·换韵)"))
        errors.extend(_check_rhyme(syllables, [5, 6], "押韵(下阕·平韵·换回)"))

        # 下阕平韵应转回上阕平声韵部；下阕仄韵须与平韵不同部（换韵）
        def tail(idx):
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
            errors.append(
                f"下阕仄韵应与平韵不同部（换韵）: 均为'{lower_ze}'"
            )
        return errors


def register_chinese_templates():
    register("zh_wujue", WujueTemplate())
    register("zh_qijue", QijueTemplate())
    register("zh_wulv", WulvTemplate())
    register("zh_qilv", QilvTemplate())
    register("zh_xiangjianhuan", XiangjianhuanTemplate())
