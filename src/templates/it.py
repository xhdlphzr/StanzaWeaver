# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

from . import PoetryTemplate, register


class TerzaRimaTemplate(PoetryTemplate):
    name = "三行体"
    language = "it"
    lines = 14
    syllables_per_line = [11] * 14

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        if len(syllables) < 3:
            return errors
        rhyme_groups = [
            ([0, 2], "ABA"),
            ([1, 3, 5], "BCB"),
            ([4, 6, 8], "CDC"),
            ([7, 9, 11], "DED"),
            ([10, 12, 13], "EE"),
        ]
        for indices, label in rhyme_groups:
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r:
                        rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")
        return errors


class OttavaRimaTemplate(PoetryTemplate):
    name = "八行体"
    language = "it"
    lines = 8
    syllables_per_line = [11] * 8

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        rhyme_groups = [
            ([0, 2, 4], "A"),
            ([1, 3, 5], "B"),
            ([6, 7], "CC"),
        ]
        for indices, label in rhyme_groups:
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r:
                        rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")
        return errors


class CanzoneTemplate(PoetryTemplate):
    name = "歌谣"
    language = "it"
    lines = 13
    syllables_per_line = [11, 11, 7, 7, 11, 11, 7, 11, 7, 11, 11, 7, 11]

    def get_syllable_constraints(self):
        return None

    def validate_full(self, poem, syllables):
        errors = []
        rhyme_groups = [
            ([0, 2, 4], "A"),
            ([1, 3, 5], "B"),
            ([6, 8, 10], "C"),
            ([7, 9, 11], "D"),
            ([12], ""),
        ]
        for indices, label in rhyme_groups:
            if len(indices) < 2:
                continue
            rhymes = []
            for idx in indices:
                if idx < len(syllables) and syllables[idx]:
                    r = syllables[idx][-1].nucleus + syllables[idx][-1].coda
                    if r:
                        rhymes.append((idx, r))
            if len(rhymes) >= 2:
                base = rhymes[0][1]
                for idx, r in rhymes[1:]:
                    if r != base:
                        errors.append(f"押韵{label}不匹配: 第{rhymes[0][0] + 1}行韵脚为'{base}'，第{idx + 1}行韵脚为'{r}'")
        return errors


def register_italian_templates():
    register("it_terza_rima", TerzaRimaTemplate())
    register("it_ottava_rima", OttavaRimaTemplate())
    register("it_canzone", CanzoneTemplate())
