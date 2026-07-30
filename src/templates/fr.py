# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from . import PoetryTemplate, register


class RondeauTemplate(PoetryTemplate):
    name = "回旋诗"
    language = "fr"
    lines = 15
    syllables_per_line = [8] * 15
    _refrain = [0, 9, 15]

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        rhyme_groups = [
            ([0, 1, 4, 5, 7, 8, 12, 13], "A"),
            ([2, 3, 6, 10, 11, 14], "B"),
        ]
        for indices, label in rhyme_groups:
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r: rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")
        base_refrain = poem[0] if len(poem) > 0 else ""
        for ref_idx in [9, 15]:
            ref_idx_0 = ref_idx - 1
            if ref_idx_0 < len(poem):
                first_words = " ".join(base_refrain.split()[:4])
                curr_words = " ".join(poem[ref_idx_0].split()[:4])
                if first_words and curr_words and first_words != curr_words:
                    errors.append(f"叠句不匹配: 第1行开头'{first_words}'与第{ref_idx}行开头'{curr_words}'不一致")
        return errors


class TrioletTemplate(PoetryTemplate):
    name = "三韵叠句诗"
    language = "fr"
    lines = 8
    syllables_per_line = [8] * 8

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        if len(poem) >= 8:
            if poem[0].strip() != poem[3].strip():
                errors.append("叠句不匹配: 第1行与第4行文本不一致")
            if poem[0].strip() != poem[7].strip():
                errors.append("叠句不匹配: 第1行与第8行文本不一致")
            if poem[1].strip() != poem[5].strip():
                errors.append("叠句不匹配: 第2行与第6行文本不一致")
        rhyme_groups = [
            ([0, 3, 4, 7], "A"),
            ([1, 2, 5, 6], "B"),
        ]
        for indices, label in rhyme_groups:
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r: rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")
        return errors


class BalladeTemplate(PoetryTemplate):
    name = "叙事歌"
    language = "fr"
    lines = 28
    syllables_per_line = [8] * 28
    _refrain_line = 27

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        rhyme_a = [0, 2, 4, 7, 8, 10, 12, 15, 16, 18, 20, 23, 24, 26, 27]
        rhyme_b = [1, 3, 5, 6, 9, 11, 13, 14, 19, 21, 22]
        rhyme_c = [17, 25]

        for label, indices in [("A", rhyme_a), ("B", rhyme_b), ("C", rhyme_c)]:
            if len(indices) < 2:
                continue
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r: rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")

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
