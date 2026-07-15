# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

from dataclasses import dataclass, field

from .syllable_counter import analyze_line, count_syllables


@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str):
        self.passed = False
        self.errors.append(msg)


class MeterValidator:
    def validate(
        self,
        poem: list[str],
        template: dict,
        template_obj: object = None,
    ) -> ValidationResult:
        language = template.get("language", "zh")
        lines_expected = template.get("lines", len(poem))
        syllables_expected = template.get("syllables_per_line", [])
        constraints = template.get("syllable_constraints", [])

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"行数不匹配: 期望 {lines_expected} 行, 实际 {len(poem)} 行"
            )

        all_syllables: list[list] = []
        min_lines = min(len(poem), len(syllables_expected))
        for i in range(min_lines):
            line = poem[i]
            expected_count = syllables_expected[i]
            actual_count = count_syllables(line, language)

            if actual_count != expected_count:
                result.add_error(
                    f"第{i + 1}行音节数不匹配: 期望 {expected_count}, 实际 {actual_count}"
                )

        if constraints:
            min_constraint_lines = min(len(poem), len(constraints))
            for i in range(min_constraint_lines):
                line = poem[i]
                line_constraints = constraints[i]
                syllables = analyze_line(line, language)
                all_syllables.append(syllables)
                min_syl = min(len(syllables), len(line_constraints))
                for j in range(min_syl):
                    if not syllables[j].match_constraint(line_constraints[j]):
                        constraint_desc = self._describe_constraint(line_constraints[j])
                        actual_desc = self._describe_syllable(syllables[j])
                        result.add_error(
                            f"第{i + 1}行第{j + 1}音节不匹配: 要求{constraint_desc}, 实际{actual_desc}"
                        )

        if template_obj is not None and hasattr(template_obj, "validate_full"):
            if not all_syllables:
                for line in poem[: len(syllables_expected)]:
                    all_syllables.append(analyze_line(line, language))
            full_errors = template_obj.validate_full(poem, all_syllables)
            for err in full_errors:
                result.add_error(err)

        return result

    def validate_count_only(
        self,
        poem: list[str],
        template: dict,
    ) -> ValidationResult:
        language = template.get("language", "zh")
        lines_expected = template.get("lines", len(poem))
        syllables_expected = template.get("syllables_per_line", [])

        result = ValidationResult()

        if len(poem) != lines_expected:
            result.add_error(
                f"行数不匹配: 期望 {lines_expected} 行, 实际 {len(poem)} 行"
            )

        min_lines = min(len(poem), len(syllables_expected))
        for i in range(min_lines):
            line = poem[i]
            expected_count = syllables_expected[i]
            actual_count = count_syllables(line, language)

            if actual_count != expected_count:
                result.add_error(
                    f"第{i + 1}行音节数不匹配: 期望 {expected_count}, 实际 {actual_count}"
                )

        return result

    def validate_line(
        self,
        line_text: str,
        line_index: int,
        template: dict,
    ) -> ValidationResult:
        language = template.get("language", "zh")
        syllables_expected = template.get("syllables_per_line", [])
        constraints = template.get("syllable_constraints", [])

        result = ValidationResult()

        if line_index < len(syllables_expected):
            expected_count = syllables_expected[line_index]
            actual_count = count_syllables(line_text, language)
            if actual_count != expected_count:
                result.add_error(
                    f"音节数不匹配: 期望 {expected_count}, 实际 {actual_count}"
                )

        if constraints and line_index < len(constraints):
            line_constraints = constraints[line_index]
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
    def _describe_constraint(c: dict) -> str:
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
    def _describe_syllable(s) -> str:
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
