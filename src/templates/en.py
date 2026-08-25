# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import re

from . import PoetryTemplate, register
from ..prosody.english import EnglishAnalyzer

_EN_ANALYZER = EnglishAnalyzer()


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


_l = _make_syl(attributes={"stress": ""})
_h = _make_syl(attributes={"stress": "heavy"})


def _last_word(line: str) -> str:
    if not line.strip():
        return ""
    return re.sub(r"[^A-Za-z0-9'-]", "", line.strip().split()[-1]).lower()


def _en_rhyme_key(line_text: str) -> str | None:
    """严格重音押韵 key：最后一个重读（主/次重音）元音起到词尾的音素串（含重音层级）。

    无重读音节的词不能作韵脚（返回 None）。"""
    word = _last_word(line_text)
    if not word:
        return None
    return _EN_ANALYZER.rhyme_tail(word)


def _check_stress_count(poem, syllables, min_stress: int, errors: list[str]) -> None:
    for i, syls in enumerate(syllables):
        stress_count = sum(1 for s in syls if s.attributes.get("stress") == "heavy")
        if stress_count < min_stress:
            errors.append(f"第{i + 1}行重音音节过少 ({stress_count})")


def _check_rhyme_group(poem, indices, label, errors) -> None:
    keys = []
    for idx in indices:
        if idx >= len(poem):
            continue
        k = _en_rhyme_key(poem[idx])
        if k is None:
            errors.append(f"第{idx + 1}行韵脚未落在主重音或次重音音节上")
            continue
        keys.append((idx, k))
    if len(keys) >= 2:
        base_idx, base = keys[0]
        for idx, k in keys[1:]:
            if k != base:
                errors.append(
                    f"押韵{label}不匹配: 第{base_idx + 1}行韵脚'{base}'，"
                    f"第{idx + 1}行韵脚'{k}'（要求自重读音节起音素及重音完全一致）"
                )


class ShakespeareSonnetTemplate(PoetryTemplate):
    name = "莎士比亚商籁体"
    language = "en"
    lines = 14
    syllables_per_line = [10] * 14
    rule_description = (
        "格律规则：每行抑扬格五音步（10音节，重音在偶数位，次重音亦算重读）；"
        "韵式 ABAB CDCD EFEF GG；每组四行内A/B两韵必须不同；"
        "押韵须为严格重音押韵：韵脚必须落在主重音或次重音音节上，"
        "且该音节起全部音素（含重音层级）完全一致。"
    )

    def get_syllable_constraints(self):
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line for _ in range(14)]

    def validate_full(self, poem, syllables):
        errors = []
        _check_stress_count(poem, syllables, 4, errors)

        rhyme_groups = [
            ("A", [0, 2], 0),
            ("B", [1, 3], 0),
            ("C", [4, 6], 1),
            ("D", [5, 7], 1),
            ("E", [8, 10], 2),
            ("F", [9, 11], 2),
            ("G", [12, 13], 3),
        ]
        quatrain_rhymes: dict[int, dict[str, str | None]] = {}
        for letter, indices, q_idx in rhyme_groups:
            if q_idx not in quatrain_rhymes:
                quatrain_rhymes[q_idx] = {}
            _check_rhyme_group(poem, indices, letter, errors)
            keys = []
            for idx in indices:
                if idx < len(poem):
                    keys.append(_en_rhyme_key(poem[idx]))
            if keys and keys[0] is not None:
                quatrain_rhymes[q_idx][letter] = keys[0]

        for q_idx in range(3):
            values = quatrain_rhymes.get(q_idx, {})
            distinct = {v for v in values.values() if v is not None}
            if len(distinct) < 2 and len(values) >= 2:
                a_rhyme = list(values.values())[0]
                errors.append(
                    f"第{q_idx + 1}段对韵: A/B 韵脚应不同，当前均为'{a_rhyme}'"
                )

        return errors


class VillanelleTemplate(PoetryTemplate):
    name = "维拉内拉诗"
    language = "en"
    lines = 19
    syllables_per_line = []
    rule_description = (
        "格律规则：全诗19行（5个三行联句+1个四行联句）；韵式 ABA ABA ABA ABA ABA ABAA；"
        "第1行(A1)在第6、12、18行原样重复，第3行(A2)在第9、15、19行原样重复；"
        "每行至少4个重读音节，总音节数不限（次重音亦算重读）；"
        "押韵须为严格重音押韵：韵脚落在主重音或次重音音节上，"
        "该音节起全部音素（含重音层级）完全一致。"
    )
    _refrain_a1 = [0, 5, 11, 17]
    _refrain_a2 = [2, 8, 14, 18]
    _rhyme_a = [0, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    _rhyme_b = [1, 4, 7, 10, 13, 16]

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        _check_stress_count(poem, syllables, 4, errors)

        if len(poem) > 0:
            base_a1 = poem[0].strip()
            for ref_idx in self._refrain_a1[1:]:
                if ref_idx < len(poem) and poem[ref_idx].strip() != base_a1:
                    errors.append(f"叠句A1不匹配: 第1行与第{ref_idx + 1}行文本不一致")
        if len(poem) > 2:
            base_a2 = poem[2].strip()
            for ref_idx in self._refrain_a2[1:]:
                if ref_idx < len(poem) and poem[ref_idx].strip() != base_a2:
                    errors.append(f"叠句A2不匹配: 第3行与第{ref_idx + 1}行文本不一致")

        _check_rhyme_group(poem, self._rhyme_a, "A", errors)
        _check_rhyme_group(poem, self._rhyme_b, "B", errors)

        a_key = _en_rhyme_key(poem[0]) if poem else None
        b_key = _en_rhyme_key(poem[1]) if len(poem) > 1 else None
        if a_key and b_key and a_key == b_key:
            errors.append(f"A/B韵脚应不同，当前均为'{a_key}'")

        return errors


class HeroicCoupletTemplate(PoetryTemplate):
    name = "英雄双行体"
    language = "en"
    lines = 2
    syllables_per_line = [10, 10]
    rule_description = (
        "格律规则：每行抑扬格五音步（10音节），全行重音音节数不少于4（次重音亦算重读）；"
        "两行末字押同韵（AA），押韵须为严格重音押韵：韵脚落在主重音或次重音音节上，"
        "该音节起全部音素（含重音层级）完全一致。"
    )

    def get_syllable_constraints(self):
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line, line]

    def validate_full(self, poem, syllables):
        errors = []
        _check_stress_count(poem, syllables, 4, errors)
        _check_rhyme_group(poem, [0, 1], "AA", errors)
        return errors


def register_english_templates():
    register("en_sonnet", ShakespeareSonnetTemplate())
    register("en_villanelle", VillanelleTemplate())
    register("en_heroic_couplet", HeroicCoupletTemplate())
