# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""法语格律模板：回旋诗、三韵叠句诗、叙事歌。

押韵采用 FrenchAnalyzer.rhyme_key（最后发音元音 + 其后辅音，静音 e 不参与）。
"""

import re
from typing import ClassVar

from ..models.syllable import Syllable
from ..prosody.french import FrenchAnalyzer
from . import ConstraintTable, PoetryTemplate, register

_FR = FrenchAnalyzer()


def _last_word(line: str) -> str:
    """取行末词（去标点、小写）。

    Args:
        line: 一行诗。

    Returns:
        行末词；空行返回空串。
    """
    if not line.strip():
        return ""
    return re.sub(r"[^a-zA-Zàâäéèêëîïôöùûüÿœ'-]", "", line.strip().split()[-1]).lower()


def _check_rhyme_group(
    poem: list[str], indices: list[int], label: str, errors: list[str]
) -> None:
    """检查一组行末词法语韵脚一致。

    Args:
        poem: 诗行列表。
        indices: 参与该韵组的行号（0-based）。
        label: 韵组名。
        errors: 错误列表（就地追加）。
    """
    keys: list[tuple[int, str]] = []
    for idx in indices:
        if idx >= len(poem):
            continue
        w = _last_word(poem[idx])
        k = _FR.rhyme_key(w) if w else ""
        if k:
            keys.append((idx, k))
    if len(keys) >= 2:
        base = keys[0][1]
        for idx, k in keys[1:]:
            if k != base:
                errors.append(
                    f"押韵{label}不匹配: 第{keys[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{k}'"
                )


class RondeauTemplate(PoetryTemplate):
    """回旋诗：15 行三节，韵式 AABBA AAB AABBA，叠句在第 9、15 行。"""

    name = "回旋诗"
    language = "fr"
    lines = 15
    syllables_per_line: ClassVar[list[int]] = [8] * 15
    _refrain_lines: ClassVar[list[int]] = [8, 14]  # 0-based: 叠句出现在第 9、15 行
    rule_description = (
        "格律规则：15行，分三节（5+4+6）；韵式 AABBA AAB AABBA（仅用A、B两韵）；"
        "每行8音节（可放宽至10，但全诗统一）；"
        "第1行首半句在第9行和第15行末尾原样重复为叠句。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：AABBA AAB AABBA 韵式 + 叠句开头 4 词一致。"""
        errors: list[str] = []
        rhyme_groups = [
            ([0, 1, 4, 5, 6, 8, 9, 10, 13, 14], "A"),
            ([2, 3, 7, 11, 12], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        base_refrain = poem[0] if len(poem) > 0 else ""
        for ref_idx in self._refrain_lines:
            if ref_idx < len(poem):
                first_words = " ".join(base_refrain.split()[:4])
                last_words = " ".join(poem[ref_idx].split()[-4:])
                if first_words and last_words and first_words != last_words:
                    errors.append(
                        f"叠句不匹配: 第1行开头'{first_words}'与第{ref_idx + 1}行末尾'{last_words}'不一致"
                    )
        return errors


class TrioletTemplate(PoetryTemplate):
    """三韵叠句诗：8 行，韵式 ABaAabAB，第 1/4/7 行与 2/8 行为叠句。"""

    name = "三韵叠句诗"
    language = "fr"
    lines = 8
    syllables_per_line = [8] * 8
    rule_description = (
        "格律规则：8行，每行8音节；韵式 ABaAabAB："
        "第1、4、7行同为A叠句原样重复，第2、8行同为B叠句原样重复；"
        "第3、5行押A韵（a），第6行押B韵（b）。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：叠句原文重复（1=4=7、2=8）+ ABaAabAB 韵式。"""
        errors: list[str] = []
        if len(poem) >= 8:
            if poem[0].strip() != poem[3].strip():
                errors.append("叠句不匹配: 第1行与第4行文本不一致")
            if poem[0].strip() != poem[6].strip():
                errors.append("叠句不匹配: 第1行与第7行文本不一致")
            if poem[1].strip() != poem[7].strip():
                errors.append("叠句不匹配: 第2行与第8行文本不一致")
        rhyme_groups = [
            ([0, 2, 3, 4, 6], "A"),
            ([1, 5, 7], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        return errors


class BalladeTemplate(PoetryTemplate):
    """叙事歌：28 行（3 节 8 行 + 4 行跋），ababbcbc 韵式，末行叠句。"""

    name = "叙事歌"
    language = "fr"
    lines = 28
    syllables_per_line: ClassVar[list[int | tuple[int, int]]] = []
    _refrain_line = 27
    rule_description = (
        "格律规则：28行（3个8行诗节+1个4行跋）；每节韵式 ababbcbc，"
        "三节及跋使用相同的A、B、C三个韵脚；"
        "每节末行（第8、16、24行）与跋末行（第28行）为完全相同的叠句；"
        "全诗每行音节数统一为8或10音节。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束（音节数在 validate_full 中统一判定）。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：全诗音节统一（8 或 10）、ababbcbc 韵式、叠句一致。"""
        errors: list[str] = []
        counts = [len(s) for s in syllables if s]
        if counts:
            base = counts[0]
            if base not in (8, 10):
                errors.append(f"叙事歌每行应为8或10音节，当前首行为{base}音节")
            for i, c in enumerate(counts):
                if c != base:
                    errors.append(f"第{i + 1}行音节数不一致: 期望{base}，实际{c}")

        # 每节 8 行 ababbcbc；末节 4 行 bcbc（0-based 行号见列表）
        rhyme_a = [0, 2, 8, 10, 16, 18]
        rhyme_b = [1, 3, 4, 6, 9, 11, 12, 14, 17, 19, 20, 22, 24, 26]
        rhyme_c = [5, 7, 13, 15, 21, 23, 25, 27]

        for label, indices in [("A", rhyme_a), ("B", rhyme_b), ("C", rhyme_c)]:
            _check_rhyme_group(poem, indices, label, errors)

        if len(poem) > 27:
            base_refrain = poem[7]
            if poem[15].strip() != base_refrain.strip():
                errors.append("叠句不匹配: 第8行与第16行文本不一致")
            if poem[23].strip() != base_refrain.strip():
                errors.append("叠句不匹配: 第8行与第24行文本不一致")
            if poem[27].strip() != base_refrain.strip():
                errors.append("叠句不匹配: 第8行与第28行文本不一致")
        return errors


def register_french_templates() -> None:
    """注册全部法语模板。"""
    register("fr_rondeau", RondeauTemplate())
    register("fr_triolet", TrioletTemplate())
    register("fr_ballade", BalladeTemplate())
