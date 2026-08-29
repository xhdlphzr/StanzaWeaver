# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""格律总校验器（MeterValidator）。

对整首诗执行三层校验：
1. 行数匹配；
2. 每行音节数（任一切分变体满足即通过）；
3. 逐位音节约束（平仄/重音/长短），任一切分变体满足即通过；
4. 模板自定义完整规则（validate_full：押韵、三平尾、孤平等）。

第 4 层不再仅取主变体，而是把每行全部发音/切分变体逐一带入审查：
对每行变体做组合搜索，存在任一组合使全部规则通过即视为合律。
"""

import itertools
from dataclasses import dataclass, field
from typing import Any, cast

# 组合搜索逐行变体时的最大组合数，超出则截断（避免意大利语 sinalefe /
# 英语多切分等导致组合数爆炸），截断后返回错误数最少的组合。
MAX_FULL_COMBOS = 20000

from ..models.syllable import Syllable
from ..templates import format_count
from .english import EnglishAnalyzer
from .syllable_counter import analyze_line, count_syllables, get_analyzer

SyllableCount = int | tuple[int, int]
Constraint = dict[str, Any]
ConstraintLine = list[Constraint]
TemplateDict = dict[str, Any]
VariantList = list[list[Syllable]]


def _count_matches(actual: int, expected: SyllableCount) -> bool:
    """判断实际音节数是否落在期望（定值或区间）。

    Args:
        actual: 实际音节数。
        expected: int 定值或 (min, max) 区间。

    Returns:
        匹配返回 True。
    """
    if isinstance(expected, (tuple, list)) and len(expected) == 2:
        return expected[0] <= actual <= expected[1]
    return actual == expected


@dataclass
class ValidationResult:
    """一次格律校验的结果。

    Attributes:
        passed: 是否全部通过。
        errors: 错误信息列表（人类可读，供 LLM 修正提示与前端展示）。
    """

    passed: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        """追加一条错误并使结果不通过。

        Args:
            msg: 错误描述。
        """
        self.passed = False
        self.errors.append(msg)


class MeterValidator:
    """多语言格律总校验器（符号层，零 AI 开销）。"""

    def validate(
        self,
        poem: list[str],
        template: TemplateDict,
        template_obj: object = None,
    ) -> ValidationResult:
        """校验整首诗。

        Args:
            poem: 诗行列表。
            template: 模板字典（to_dict() 结果）。
            template_obj: 模板对象（含 validate_full 时执行完整规则检查）。

        Returns:
            校验结果（含全部错误）。
        """
        language = str(template.get("language", "zh"))
        lines_expected = int(template.get("lines", len(poem)))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )
        constraints_raw = template.get("syllable_constraints", [])
        constraints: list[ConstraintLine] = (
            list(constraints_raw) if constraints_raw else []
        )

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"行数不匹配: 期望 {lines_expected} 行, 实际 {len(poem)} 行"
            )

        all_syllables: list[VariantList] = []
        for i in range(len(poem)):
            analyzer = get_analyzer(language)
            if hasattr(analyzer, "analyze_line_variants"):
                # 多音语言（zh/en/it/la）：保留全部切分变体，任一满足格律即通过
                all_syllables.append(
                    cast("VariantList", analyzer.analyze_line_variants(poem[i]))
                )
            else:
                all_syllables.append([analyze_line(poem[i], language)])

        for i in range(min(len(poem), len(syllables_expected))):
            expected_count = syllables_expected[i]
            if not any(
                _count_matches(len(v), expected_count) for v in all_syllables[i]
            ):
                actual_count = len(all_syllables[i][0])
                result.add_error(
                    f"第{i + 1}行音节数不匹配: 期望 {format_count(expected_count)}, 实际 {actual_count}"
                )

        if constraints:
            min_constraint_lines = min(len(poem), len(constraints))
            for i in range(min_constraint_lines):
                line_constraints = constraints[i]
                if any(
                    self._line_matches_variant(v, line_constraints)
                    for v in all_syllables[i]
                ):
                    continue
                syllables = all_syllables[i][0]
                min_syl = min(len(syllables), len(line_constraints))
                for j in range(min_syl):
                    if not syllables[j].match_constraint(line_constraints[j]):
                        constraint_desc = self._describe_constraint(line_constraints[j])
                        actual_desc = self._describe_syllable(syllables[j])
                        result.add_error(
                            f"第{i + 1}行第{j + 1}音节不匹配: 要求{constraint_desc}, 实际{actual_desc}"
                        )

        if template_obj is not None and hasattr(template_obj, "validate_full"):
            full_errors = self._validate_full_variants(
                template_obj, poem, all_syllables, language
            )
            for err in full_errors:
                result.add_error(err)

        return result

    @staticmethod
    def _line_matches_variant(
        variant: list[Syllable], line_constraints: ConstraintLine
    ) -> bool:
        """判断一行音节是否满足整行逐位约束。

        Args:
            variant: 一行的一个音节切分变体。
            line_constraints: 该行的逐位约束。

        Returns:
            全部约束满足返回 True。
        """
        min_syl = min(len(variant), len(line_constraints))
        for j in range(min_syl):
            if not variant[j].match_constraint(line_constraints[j]):
                return False
        return True

    @staticmethod
    def _order_variants(
        language: str, variants: list[list[Syllable]]
    ) -> list[list[Syllable]]:
        """为组合搜索排序每行变体（主变体优先，作为首个被尝试的组合）。

        Args:
            language: 语言代码。
            variants: 该行的候选切分列表。

        Returns:
            排序后的变体列表（主变体在前）。
        """
        if language == "en":
            return sorted(
                variants,
                key=lambda v: sum(
                    1 for s in v if s.attributes.get("stress") == "heavy"
                ),
                reverse=True,
            )
        return variants

    def _validate_full_variants(
        self,
        template_obj: Any,
        poem: list[str],
        all_syllables: list[list[list[Syllable]]],
        language: str,
    ) -> list[str]:
        """对每行全部发音/切分变体做组合搜索，任一组合通过即视为合律。

        不再仅取主变体：把每个变体逐一带入 validate_full 审查。若存在一个
        逐行变体组合使全部格律规则通过，则返回空错误；否则返回错误数最少的
        组合对应的错误（兜底为各语言主变体）。组合数过大时截断于
        ``MAX_FULL_COMBOS``，避免意大利语 sinalefe / 英语多切分导致的爆炸。

        Args:
            template_obj: 模板对象（含 validate_full）。
            poem: 诗行文本（押韵/叠句等文本级规则使用）。
            all_syllables: 每行一个变体列表（VariantList）。
            language: 语言代码。

        Returns:
            错误列表；存在合律组合时返回空列表。
        """
        line_variants: list[list[list[Syllable]]] = []
        for vs in all_syllables:
            if vs:
                line_variants.append(self._order_variants(language, list(vs)))
            else:
                line_variants.append([[]])
        best: list[str] | None = None
        best_len: int | None = None
        for tried, combo in enumerate(itertools.product(*line_variants), start=1):
            errs = template_obj.validate_full(poem, list(combo))
            if not errs:
                return []
            if best_len is None or len(errs) < best_len:
                best_len = len(errs)
                best = errs
            if tried >= MAX_FULL_COMBOS:
                break
        return best if best is not None else []

    def validate_count_only(
        self,
        poem: list[str],
        template: TemplateDict,
    ) -> ValidationResult:
        """仅校验行数与每行音节数（初稿阶段的快速检查）。

        Args:
            poem: 诗行列表。
            template: 模板字典。

        Returns:
            校验结果。
        """
        language = str(template.get("language", "zh"))
        lines_expected = int(template.get("lines", len(poem)))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"行数不匹配: 期望 {lines_expected} 行, 实际 {len(poem)} 行"
            )

        min_lines = min(len(poem), len(syllables_expected))
        for i in range(min_lines):
            line = poem[i]
            expected_count = syllables_expected[i]

            if language == "en":
                # 英语存在多音词，取任一发音变体满足即可（与完整校验一致）
                variants = EnglishAnalyzer().analyze_line_variants(line)
                ok = any(_count_matches(len(v), expected_count) for v in variants)
                actual_count = len(variants[0]) if variants else 0
            else:
                actual_count = count_syllables(line, language)
                ok = _count_matches(actual_count, expected_count)

            if not ok:
                result.add_error(
                    f"第{i + 1}行音节数不匹配: 期望 {format_count(expected_count)}, 实际 {actual_count}"
                )

        return result

    def validate_line(
        self,
        line_text: str,
        line_index: int,
        template: TemplateDict,
    ) -> ValidationResult:
        """校验单行（refine_line 工具的前置检查）。

        Args:
            line_text: 新行文本。
            line_index: 行号（0-based）。
            template: 模板字典。

        Returns:
            校验结果。
        """
        language = str(template.get("language", "zh"))
        syllables_expected: list[SyllableCount] = list(
            template.get("syllables_per_line", [])
        )
        constraints_raw = template.get("syllable_constraints", [])
        constraints: list[ConstraintLine] = (
            list(constraints_raw) if constraints_raw else []
        )

        result = ValidationResult()

        if line_index < len(syllables_expected):
            expected_count = syllables_expected[line_index]
            if language == "en":
                variants = get_analyzer(language).analyze_line_variants(line_text)  # type: ignore[attr-defined]
                ok = any(_count_matches(len(v), expected_count) for v in variants)
                actual_count = len(variants[0]) if variants else 0
            else:
                actual_count = count_syllables(line_text, language)
                ok = _count_matches(actual_count, expected_count)
            if not ok:
                result.add_error(
                    f"音节数不匹配: 期望 {format_count(expected_count)}, 实际 {actual_count}"
                )

        if constraints and line_index < len(constraints):
            line_constraints = constraints[line_index]
            if language == "en":
                variants = get_analyzer(language).analyze_line_variants(line_text)  # type: ignore[attr-defined]
                if any(
                    self._line_matches_variant(v, line_constraints) for v in variants
                ):
                    return result
                syllables = variants[0]
            else:
                syllables = analyze_line(line_text, language)
            min_syl = min(len(syllables), len(line_constraints))
            for j in range(min_syl):
                if not syllables[j].match_constraint(line_constraints[j]):
                    constraint_desc = self._describe_constraint(line_constraints[j])
                    actual_desc = self._describe_syllable(syllables[j])
                    result.add_error(
                        f"第{j + 1}音节: 要求{constraint_desc}, 实际{actual_desc}"
                    )

        return result

    @staticmethod
    def _describe_constraint(c: Constraint) -> str:
        """约束的人类可读描述。

        Args:
            c: 约束字典。

        Returns:
            如 "声母=zh,tone=平"；无约束返回 "无约束"。
        """
        parts = []
        if c.get("onset"):
            parts.append(f"声母={c['onset']}")
        if c.get("nucleus"):
            parts.append(f"韵母={c['nucleus']}")
        if c.get("coda"):
            parts.append(f"韵尾={c['coda']}")
        for k, v in c.get("attributes", {}).items():
            if v:
                parts.append(f"{k}={v}")
        return ",".join(parts) if parts else "无约束"

    @staticmethod
    def _describe_syllable(s: Syllable) -> str:
        """音节的人类可读描述。

        Args:
            s: 音节。

        Returns:
            如 "声母=zh,tone=仄"；全空返回 "空"。
        """
        parts = []
        if s.onset:
            parts.append(f"声母={s.onset}")
        if s.nucleus:
            parts.append(f"韵母={s.nucleus}")
        if s.coda:
            parts.append(f"韵尾={s.coda}")
        for k, v in s.attributes.items():
            if v:
                parts.append(f"{k}={v}")
        return ",".join(parts) if parts else "空"
