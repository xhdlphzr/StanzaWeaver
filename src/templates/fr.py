# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from . import PoetryTemplate, register
from ..prosody.french import FrenchAnalyzer

_FR = FrenchAnalyzer()


def _last_word(line: str) -> str:
    if not line.strip():
        return ""
    return re.sub(r"[^a-zA-Zàâäéèêëîïôöùûüÿœ'-]", "", line.strip().split()[-1]).lower()


def _check_rhyme_group(poem, indices, label, errors) -> None:
    """法语韵脚：取行末词最后一个发音元音+其后辅音（静音 e 不参与）。"""
    keys = []
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
    name = "回旋诗"
    language = "fr"
    lines = 15
    syllables_per_line = [8] * 15
    _refrain_lines = (8, 14)  # 0-based: 叠句出现在第 9、15 行
    rule_description = (
        "格律规则：15行，分三节（5+4+6）；韵式 AABBA AAB AABBA（仅用A、B两韵）；"
        "每行8音节（可放宽至10，但全诗统一）；"
        "第1行首半句在第9行和第15行末尾原样重复为叠句。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        # 经典回旋诗: 0:A 1:A 2:B 3:B 4:A | 5:A 6:A 7:B | 8:叠句 | 9:A 10:A 11:B 12:B 13:A | 14:叠句
        rhyme_groups = [
            ([0, 1, 4, 5, 6, 9, 10, 13], "A"),
            ([2, 3, 7, 11, 12], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        base_refrain = poem[0] if len(poem) > 0 else ""
        for ref_idx in self._refrain_lines:
            if ref_idx < len(poem):
                first_words = " ".join(base_refrain.split()[:4])
                curr_words = " ".join(poem[ref_idx].split()[:4])
                if first_words and curr_words and first_words != curr_words:
                    errors.append(f"叠句不匹配: 第1行开头'{first_words}'与第{ref_idx + 1}行开头'{curr_words}'不一致")
        return errors


class TrioletTemplate(PoetryTemplate):
    name = "三韵叠句诗"
    language = "fr"
    lines = 8
    syllables_per_line = [8] * 8
    rule_description = (
        "格律规则：8行，每行8音节；韵式 ABaAabAB："
        "第1、4、7行同为A叠句原样重复，第2、8行同为B叠句原样重复；"
        "第3、5行押A韵（a），第6行押B韵（b）。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        if len(poem) >= 8:
            if poem[0].strip() != poem[3].strip():
                errors.append("叠句不匹配: 第1行与第4行文本不一致")
            if poem[0].strip() != poem[6].strip():
                errors.append("叠句不匹配: 第1行与第7行文本不一致")
            if poem[1].strip() != poem[7].strip():
                errors.append("叠句不匹配: 第2行与第8行文本不一致")
        # ABaAabAB: A 韵 = 1,3,4,5,7 行(叠句A+a)；B 韵 = 2,6,8 行(叠句B+b)
        rhyme_groups = [
            ([0, 2, 3, 4, 6], "A"),
            ([1, 5, 7], "B"),
        ]
        for indices, label in rhyme_groups:
            _check_rhyme_group(poem, indices, label, errors)
        return errors


class BalladeTemplate(PoetryTemplate):
    name = "叙事歌"
    language = "fr"
    lines = 28
    syllables_per_line = []
    _refrain_line = 27
    rule_description = (
        "格律规则：28行（3个8行诗节+1个4行跋）；每节韵式 ababbcbc，"
        "三节及跋使用相同的A、B、C三个韵脚；"
        "每节末行（第8、16、24行）与跋末行（第28行）为完全相同的叠句；"
        "全诗每行音节数统一为8或10音节。"
    )

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        # 全诗每行音节数统一（8 或 10）
        counts = [len(s) for s in syllables if s]
        if counts:
            base = counts[0]
            if base not in (8, 10):
                errors.append(f"叙事歌每行应为8或10音节，当前首行为{base}音节")
            for i, c in enumerate(counts):
                if c != base:
                    errors.append(f"第{i + 1}行音节数不一致: 期望{base}，实际{c}")

        # 传统叙事歌韵式: 每节 8 行 ababbcbc，结句(第 8/16/24 行)与末节(第 28 行)为叠句，押 c 韵；末节 4 行 bcbc
        # 0-based 行号: 各节 a=0,2 / b=1,3,4,6 / c=5,7；末节 b=24,26 / c=25,27
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


def register_french_templates():
    register("fr_rondeau", RondeauTemplate())
    register("fr_triolet", TrioletTemplate())
    register("fr_ballade", BalladeTemplate())
