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


_l = _make_syl(attributes={"stress": "light"})
_h = _make_syl(attributes={"stress": "heavy"})


class SonnetTemplate(PoetryTemplate):
    name = "十四行诗"
    language = "en"
    lines = 14
    syllables_per_line = [10] * 14

    def get_syllable_constraints(self):
        line = [_l, _h, _l, _h, _l, _h, _l, _h, _l, _h]
        return [line for _ in range(14)]

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            stress_count = sum(1 for s in syls if s.attributes.get("stress") == "heavy")
            if stress_count < 3:
                errors.append(f"第{i + 1}行重音音节过少 ({stress_count}/10)")

        quatrains = [
            ("A", [0, 2], 0), ("B", [1, 3], 0),
            ("C", [4, 6], 1), ("D", [5, 7], 1),
            ("E", [8, 10], 2), ("F", [9, 11], 2),
            ("G", [12, 13], 3),
        ]
        quatrain_rhymes: dict[int, dict[str, str]] = {}

        for letter, indices, q_idx in quatrains:
            if q_idx not in quatrain_rhymes:
                quatrain_rhymes[q_idx] = {}
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    last = syllables[idx][-1]
                    rhyme_key = last.nucleus + last.coda
                    rhymes.append((idx, rhyme_key))
            if len(rhymes) >= 2:
                base_rhyme = rhymes[0][1]
                quatrain_rhymes[q_idx][letter] = base_rhyme
                for idx, r in rhymes[1:]:
                    if r and base_rhyme and r != base_rhyme:
                        errors.append(
                            f"押韵不匹配 {letter}: 第{rhymes[0][0] + 1}行韵脚为'{base_rhyme}'，第{idx + 1}行韵脚为'{r}'"
                        )

        for q_idx in range(3):
            if q_idx in quatrain_rhymes:
                rhyme_set = set(quatrain_rhymes[q_idx].values())
                if len(rhyme_set) < 2:
                    a_rhyme = list(quatrain_rhymes[q_idx].values())[0]
                    errors.append(f"第{q_idx + 1}段对韵: A/B 韵脚应不同，当前均为'{a_rhyme}'")

        return errors


def register_english_templates():
    register("en_sonnet", SonnetTemplate())
