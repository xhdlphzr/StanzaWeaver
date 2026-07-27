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


def _check_sanpingwei(syllables: list[Syllable]) -> list[str]:
    errors = []
    if len(syllables) >= 3:
        last3 = [s.attributes.get("tone", "") for s in syllables[-3:]]
        if last3 == ["平", "平", "平"]:
            errors.append("三平尾: 末三字皆为平声，不合律")
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
            rhyme_keys.append((line_idx, last.nucleus + last.coda))
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

    def get_syllable_constraints(self):
        return [
            [_tone("仄"), _tone("仄"), _tone("平"), _tone("平"), _tone("仄")],
            [_tone("平"), _tone("平"), _tone("仄"), _tone("仄"), _tone("平")],
            [_tone("平"), _tone("平"), _tone("平"), _tone("仄"), _tone("仄")],
            [_tone("仄"), _tone("仄"), _tone("仄"), _tone("平"), _tone("平")],
        ]

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class QijueTemplate(PoetryTemplate):
    name = "七言绝句"
    language = "zh"
    lines = 4
    syllables_per_line = [7, 7, 7, 7]

    def get_syllable_constraints(self):
        _z, _p = _tone("仄"), _tone("平")
        return [
            [_z, _z, _p, _p, _p, _z, _z],
            [_p, _p, _z, _z, _z, _p, _p],
            [_p, _p, _z, _z, _p, _p, _z],
            [_z, _z, _p, _p, _z, _z, _p],
        ]

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
        errors.extend(_check_rhyme(syllables, [1, 3], "押韵(二四行)"))
        return errors


class WulvTemplate(PoetryTemplate):
    name = "五言律诗"
    language = "zh"
    lines = 8
    syllables_per_line = [5] * 8

    def get_syllable_constraints(self):
        _z, _p = _tone("仄"), _tone("平")
        return [
            [_z, _z, _p, _p, _z],
            [_p, _p, _z, _z, _p],
            [_p, _p, _p, _z, _z],
            [_z, _z, _z, _p, _p],
            [_z, _z, _p, _p, _z],
            [_p, _p, _z, _z, _p],
            [_p, _p, _p, _z, _z],
            [_z, _z, _z, _p, _p],
        ]

    def validate_full(self, poem, syllables):
        errors = []
        constraints = self.get_syllable_constraints()
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
            errors.extend(_check_lv_alternation(syls, i, constraints))
        errors.extend(_check_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class QilvTemplate(PoetryTemplate):
    name = "七言律诗"
    language = "zh"
    lines = 8
    syllables_per_line = [7] * 8

    def get_syllable_constraints(self):
        _z, _p = _tone("仄"), _tone("平")
        return [
            [_z, _z, _p, _p, _p, _z, _z],
            [_p, _p, _z, _z, _z, _p, _p],
            [_p, _p, _z, _z, _p, _p, _z],
            [_z, _z, _p, _p, _z, _z, _p],
            [_z, _z, _p, _p, _p, _z, _z],
            [_p, _p, _z, _z, _z, _p, _p],
            [_p, _p, _z, _z, _p, _p, _z],
            [_z, _z, _p, _p, _z, _z, _p],
        ]

    def validate_full(self, poem, syllables):
        errors = []
        constraints = self.get_syllable_constraints()
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
            errors.extend(_check_guping(syls))
            errors.extend(_check_lv_alternation(syls, i, constraints))
        errors.extend(_check_rhyme(syllables, [1, 3, 5, 7], "押韵(二四六八行)"))
        return errors


class RumenglingTemplate(PoetryTemplate):
    name = "如梦令"
    language = "zh"
    lines = 6
    syllables_per_line = [5, 6, 5, 6, 2, 6]

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            errors.extend(_check_sanpingwei(syls))
        errors.extend(_check_rhyme(syllables, [1, 3, 5], "押韵"))
        return errors


def register_chinese_templates():
    register("zh_wujue", WujueTemplate())
    register("zh_qijue", QijueTemplate())
    register("zh_wulv", WulvTemplate())
    register("zh_qilv", QilvTemplate())
    register("zh_rumengling", RumenglingTemplate())
