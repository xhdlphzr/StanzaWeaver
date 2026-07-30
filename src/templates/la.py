# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from . import PoetryTemplate, register


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


_L = _make_syl(attributes={"length": "long"})
_S = _make_syl(attributes={"length": "short"})


class HexameterTemplate(PoetryTemplate):
    name = "六步格"
    language = "la"
    lines = 1
    syllables_per_line = [17]

    def get_syllable_constraints(self):
        return [[
            _L, _S, _S, _L, _S, _S, _L, _S, _S, _L, _S, _S,
            _L, _L, _L, _L, {},
        ]]

    def validate_full(self, poem, syllables):
        errors = []
        if not syllables or not syllables[0]:
            return errors
        syls = syllables[0]
        if len(syls) < 13:
            errors.append(f"音节数不足: 至少13个，实际{len(syls)}个")
        feet = [(0, 3), (3, 6), (6, 9), (9, 12), (12, 14), (14, 17)]
        for foot_idx, (start, end) in enumerate(feet):
            if end > len(syls):
                continue
            foot = syls[start:end]
            length_sum = sum(1 for s in foot if s.attributes.get("length") == "long")
            if foot_idx <= 3:
                if length_sum < 1:
                    errors.append(f"第{foot_idx + 1}音步无效: 至少需要1个长音节")
            elif foot_idx == 4:
                if length_sum < 2:
                    errors.append(f"第5音步应为扬扬格(spondee)，当前长音节={length_sum}")
        return errors


class DistichonTemplate(PoetryTemplate):
    name = "哀歌双行体"
    language = "la"
    lines = 2
    syllables_per_line = [17, 14]

    def get_syllable_constraints(self):
        return [
            [_L, _S, _S, _L, _S, _S, _L, _S, _S, _L, _S, _S, _L, _L, _L, _L, {}],
            [_L, _S, _S, _L, _S, _S, _L, {}, _L, _S, _S, _L, _S, _S],
        ]

    def validate_full(self, poem, syllables):
        errors = []
        if not syllables or len(syllables) < 2:
            return errors
        hex_syls = syllables[0]
        pent_syls = syllables[1]
        for i, s in enumerate(hex_syls[:12]):
            if s.attributes.get("length", "") == "short":
                if i % 3 == 0:
                    errors.append(f"第1行第{i + 1}音节: 六步格第1位应为长音节")
        for i, s in enumerate(pent_syls[:6]):
            if s.attributes.get("length") == "short" and i % 3 == 0:
                errors.append(f"第2行第{i + 1}音节: 应为长音节")
        if len(poem) >= 2:
            if syllables[0] and syllables[1]:
                r0 = syllables[0][-1].nucleus + syllables[0][-1].coda
                r1 = syllables[1][-1].nucleus + syllables[1][-1].coda
                if r0 and r1 and r0 != r1:
                    errors.append(f"押韵不匹配: 第1行韵脚为'{r0}'，第2行韵脚为'{r1}'")
        return errors


class HendecasyllabusTemplate(PoetryTemplate):
    name = "十一音节诗"
    language = "la"
    lines = 1
    syllables_per_line = [11]

    def get_syllable_constraints(self):
        return [[
            {}, {}, _L, _S, _S, _L, _S, _L, _S, _L, _S,
        ]]

    def validate_full(self, poem, syllables):
        errors = []
        if not syllables or not syllables[0]:
            return errors
        syls = syllables[0]
        if len(syls) < 11:
            errors.append(f"音节数不足: 需要11个，实际{len(syls)}个")
        patterns = [
            (2, "long"), (5, "long"), (7, "long"), (9, "long"),
        ]
        for pos, expected in patterns:
            if pos < len(syls):
                actual = syls[pos].attributes.get("length", "")
                if actual and actual != expected:
                    errors.append(f"第{pos + 1}音节应为长音节，实际为{actual}")
        return errors


def register_latin_templates():
    register("la_hexameter", HexameterTemplate())
    register("la_distichon", DistichonTemplate())
    register("la_hendecasyllabus", HendecasyllabusTemplate())
