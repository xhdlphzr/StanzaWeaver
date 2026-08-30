# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""英语格律模板：莎士比亚商籁体、维拉内拉诗、英雄双行体。

押韵采用严格重音匹配：韵脚必须落在主/次重音音节上，且该音节起的
全部音素（含重音层级）完全一致，任一发音满足押韵即通过
（由 EnglishAnalyzer.rhyme_tails 实现）。
"""

import re
from typing import Any, ClassVar

from ..models.syllable import Syllable
from ..prosody.english import EnglishAnalyzer
from . import ConstraintTable, PoetryTemplate, register

_EN_ANALYZER = EnglishAnalyzer()


def _make_syl(**kwargs: Any) -> dict[str, Any]:
    """构造逐位约束字典。

    Args:
        **kwargs: 可含 onset/nucleus/coda 及 attributes。

    Returns:
        约束字典。
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


_l: dict[str, Any] = _make_syl(attributes={"stress": "light"})
_h: dict[str, Any] = _make_syl(attributes={"stress": "heavy"})


def _last_word(line: str) -> str:
    """取行末词（去标点、小写）。

    Args:
        line: 一行诗。

    Returns:
        行末词；空行返回空串。
    """
    if not line.strip():
        return ""
    return re.sub(r"[^A-Za-z0-9'-]", "", line.strip().split()[-1]).lower()


def _en_rhyme_key(line_text: str) -> tuple[str, ...] | None:
    """严格重音押韵 key：行末词全部发音中"自重读音节起的音素串"集合。

    押韵须为严格重音匹配（含重音层级），且任一发音满足押韵即通过，
    故返回去重后的尾串元组（可哈希，便于集合运算）。

    Args:
        line_text: 一行诗。

    Returns:
        押韵尾串元组；行末词无重读音节时返回 None（不能作韵脚）。
    """
    word = _last_word(line_text)
    if not word:
        return None
    tails = _EN_ANALYZER.rhyme_tails(word)
    if not tails:
        return None
    return tuple(sorted(set(tails)))


def _check_stress_count(
    poem: list[str], syllables: list[list[Syllable]], min_stress: int, errors: list[str]
) -> None:
    """检查每行重读音节数下限（次重音亦计入）。

    Args:
        poem: 诗行列表。
        syllables: 各行音节。
        min_stress: 最少重读音节数。
        errors: 错误列表（就地追加）。
    """
    for i, syls in enumerate(syllables):
        stress_count = sum(1 for s in syls if s.attributes.get("stress") == "heavy")
        if stress_count < min_stress:
            errors.append(f"第{i + 1}行重音音节过少 ({stress_count})")


def _check_rhyme_group(
    poem: list[str], indices: list[int], label: str, errors: list[str]
) -> None:
    """检查一组行严格重音押韵一致（组内所有行共享至少一个韵尾）。

    Args:
        poem: 诗行列表。
        indices: 参与该韵组的行号（0-based）。
        label: 韵组名（A/B/AA 等）。
        errors: 错误列表（就地追加）。
    """
    keys: list[tuple[int, tuple[str, ...]]] = []
    for idx in indices:
        if idx >= len(poem):
            continue
        k = _en_rhyme_key(poem[idx])
        if k is None:
            errors.append(f"第{idx + 1}行韵脚未落在主重音或次重音音节上")
            continue
        keys.append((idx, k))
    if len(keys) >= 2:
        common: set[str] = set(keys[0][1])
        for _, k in keys[1:]:
            common &= set(k)
        if not common:
            first_idx, first_key = keys[0]
            last_idx, last_key = keys[-1]
            errors.append(
                f"押韵{label}不匹配: 第{first_idx + 1}行韵脚{first_key}，"
                f"第{last_idx + 1}行韵脚{last_key}"
                f"（要求组内所有行共享一个自重读音节起的音素尾串）"
            )


class ShakespeareSonnetTemplate(PoetryTemplate):
    """莎士比亚商籁体：14 行抑扬格五音步，韵式 ABAB CDCD EFEF GG。"""

    name = "莎士比亚商籁体"
    language = "en"
    lines = 14
    syllables_per_line: ClassVar[list[int]] = [10] * 14
    rule_description = (
        "格律规则：每行抑扬格五音步（10音节，重音在偶数位，次重音亦算重读）；"
        "韵式 ABAB CDCD EFEF GG；每组四行内A/B两韵必须不同；"
        "押韵须为严格重音押韵：韵脚必须落在主重音或次重音音节上，"
        "且该音节起全部音素（含重音层级）完全一致。"
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """抑扬格逐位约束：奇数位轻、偶数位重。

        Returns:
            逐位音节约束表。
        """
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line for _ in range(14)]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：重音下限、ABAB CDCD EFEF GG 韵式、组内 A/B 韵不同。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
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
        quatrain_rhymes: dict[int, dict[str, tuple[str, ...] | None]] = {}
        for letter, indices, q_idx in rhyme_groups:
            if q_idx not in quatrain_rhymes:
                quatrain_rhymes[q_idx] = {}
            _check_rhyme_group(poem, indices, letter, errors)
            for idx in indices:
                if idx < len(poem):
                    quatrain_rhymes[q_idx][letter] = _en_rhyme_key(poem[idx])

        for q_idx in range(3):
            values = quatrain_rhymes.get(q_idx, {})
            present = [v for v in values.values() if v is not None]
            if len(present) >= 2:
                for i in range(len(present)):
                    for j in range(i + 1, len(present)):
                        if not set(present[i]).isdisjoint(present[j]):
                            errors.append(
                                f"第{q_idx + 1}段对韵: A/B 韵脚应不同，"
                                f"当前共享韵尾{set(present[i]) & set(present[j])}"
                            )

        return errors


class VillanelleTemplate(PoetryTemplate):
    """维拉内拉诗：19 行，韵式 ABA…ABAA，两叠句循环，音节数不限。"""

    name = "维拉内拉诗"
    language = "en"
    lines = 19
    syllables_per_line: ClassVar[list[int | tuple[int, int]]] = []
    rule_description = (
        "格律规则：全诗19行（5个三行联句+1个四行联句）；韵式 ABA ABA ABA ABA ABA ABAA；"
        "第1行(A1)在第6、12、18行原样重复，第3行(A2)在第9、15、19行原样重复；"
        "每行至少4个重读音节，总音节数不限（次重音亦算重读）；"
        "押韵须为严格重音押韵：韵脚落在主重音或次重音音节上，"
        "该音节起全部音素（含重音层级）完全一致。"
    )
    _refrain_a1: ClassVar[list[int]] = [0, 5, 11, 17]
    _refrain_a2: ClassVar[list[int]] = [2, 8, 14, 18]
    _rhyme_a: ClassVar[list[int]] = [0, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    _rhyme_b: ClassVar[list[int]] = [1, 4, 7, 10, 13, 16]

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无逐位约束（只要求每行 ≥4 重读音节）。

        Returns:
            逐位音节约束表。
        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：重音下限、叠句原文重复、A/B 两韵及互异。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
        _check_stress_count(poem, syllables, 4, errors)

        if len(poem) > 0:
            base_a1 = _norm_refrain(poem[0])
            for ref_idx in self._refrain_a1[1:]:
                if ref_idx < len(poem) and _norm_refrain(poem[ref_idx]) != base_a1:
                    errors.append(f"叠句A1不匹配: 第1行与第{ref_idx + 1}行文本不一致")
        if len(poem) > 2:
            base_a2 = _norm_refrain(poem[2])
            for ref_idx in self._refrain_a2[1:]:
                if ref_idx < len(poem) and _norm_refrain(poem[ref_idx]) != base_a2:
                    errors.append(f"叠句A2不匹配: 第3行与第{ref_idx + 1}行文本不一致")

        _check_rhyme_group(poem, self._rhyme_a, "A", errors)
        _check_rhyme_group(poem, self._rhyme_b, "B", errors)

        a_key = _en_rhyme_key(poem[0]) if poem else None
        b_key = _en_rhyme_key(poem[1]) if len(poem) > 1 else None
        if a_key and b_key and not set(a_key).isdisjoint(b_key):
            errors.append(f"A/B韵脚应不同，当前共享韵尾{set(a_key) & set(b_key)}")

        return errors


def _norm_refrain(line: str) -> str:
    """叠句归一化：折叠空白并忽略大小写。

    Args:
        line: 一行诗。

    Returns:
        归一化后的文本。
    """
    return " ".join(line.split()).casefold()


class HeroicCoupletTemplate(PoetryTemplate):
    """英雄双行体：两行抑扬格五音步，AA 严格重音押韵，可连续堆叠。"""

    name = "英雄双行体"
    language = "en"
    lines = 2
    syllables_per_line: ClassVar[list[int]] = [10, 10]
    rule_description = (
        "格律规则：每行抑扬格五音步（10音节），全行重音音节数不少于4（次重音亦算重读）；"
        "两行末字押同韵（AA），押韵须为严格重音押韵：韵脚落在主重音或次重音音节上，"
        "该音节起全部音素（含重音层级）完全一致。"
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """抑扬格逐位约束。

        Returns:
            逐位音节约束表。
        """
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line, line]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：重音下限 + AA 押韵。

        Args:
            poem: 诗行列表。
            syllables: 各行音节列表。

        Returns:
            错误信息列表（空列表表示通过）。
        """
        errors: list[str] = []
        _check_stress_count(poem, syllables, 4, errors)
        _check_rhyme_group(poem, [0, 1], "AA", errors)
        return errors


def register_english_templates() -> None:
    """注册全部英语模板。"""
    register("en_sonnet", ShakespeareSonnetTemplate())
    register("en_villanelle", VillanelleTemplate())
    register("en_heroic_couplet", HeroicCoupletTemplate())
