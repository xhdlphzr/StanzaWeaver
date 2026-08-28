"""格律总校验器（MeterValidator）。

对整首诗执行三层校验：
1. 行数匹配；
2. 每行音节数（英语按多音变体任选其一满足即可）；
3. 逐位音节约束（平仄/重音/长短），英语同样支持任一变体；
4. 模板自定义完整规则（validate_full：押韵、三平尾、孤平等）。
"""

from dataclasses import dataclass, field
from typing import Any

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
            if language == "en":
                # 英语多音词：保留全部发音的组合切分，任一变体满足格律即通过
                all_syllables.append(
                    get_analyzer(language).analyze_line_variants(poem[i])  # type: ignore[attr-defined]
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
                        break

        if template_obj is not None and hasattr(template_obj, "validate_full"):
            primary = [v[0] for v in all_syllables]
            full_errors = template_obj.validate_full(poem, primary)
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
            actual_count = count_syllables(line_text, language)
            if not _count_matches(actual_count, expected_count):
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
