# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
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
    name = "Sonnet (Shakespearean)"
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
                errors.append(f"第{i+1}行重音音节过少 ({stress_count}/10)")
        rhyme_groups = [
            ([0, 2], "ABAB quatrain 1"),
            ([1, 3], ""),
            ([4, 6], "CDCD quatrain 2"),
            ([5, 7], ""),
            ([8, 10], "EFEF quatrain 3"),
            ([9, 11], ""),
            ([12, 13], "GG couplet"),
        ]
        for line_indices, label in rhyme_groups:
            if len(line_indices) < 2:
                continue
            rhymes = []
            for idx in line_indices:
                if idx < len(syllables) and syllables[idx]:
                    last = syllables[idx][-1]
                    rhymes.append((idx, last.nucleus + last.coda))
            if len(rhymes) >= 2:
                base_rhyme = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r and base_rhyme and r != base_rhyme:
                        desc = f" ({label})" if label else ""
                        errors.append(f"押韵不匹配{desc}: 第{rhymes[0][0]+1}行韵脚为'{base_rhyme}'，第{idx+1}行韵脚为'{r}'")
        return errors


class HaikuTemplate(PoetryTemplate):
    name = "Haiku"
    language = "en"
    lines = 3
    syllables_per_line = [5, 7, 5]

    def validate_full(self, poem, syllables):
        errors = []
        for i, syls in enumerate(syllables):
            expected = self.syllables_per_line[i] if i < len(self.syllables_per_line) else 0
            if len(syls) != expected:
                errors.append(f"第{i+1}行音节数不匹配: 期望 {expected}, 实际 {len(syls)}")
        return errors


def register_english_templates():
    register("en_sonnet", SonnetTemplate())
    register("en_haiku", HaikuTemplate())
