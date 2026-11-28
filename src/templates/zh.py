# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Chinese metrical templates for regulated verse and ci tunes.

Covers five- and seven-character quatrains and regulated poems, plus the ci
tunes Xiangjianhuan, Rumengling, Langtaosha, and Qingpingyue.

Implements the symbolic-level rules of regulated verse and ci tunes:
- tone skeleton: positions 2/4(6) alternate within a line, oppose within a
  couplet, and adhere across couplets; leading lines end oblique, responding
  lines end level;
- rhyme: even lines use level-tone rhyme (single rhyme throughout, per the 16
  rhyme groups of *Zhonghua Tongyun*); the first line may join the rhyme; ci
  tunes change rhyme per their patterns;
- prohibitions: three level-tone tail, isolated level (three oblique-tone tail
  is not a prohibition).
"""

from typing import Any, ClassVar

from ..models.syllable import Syllable
from . import ConstraintTable, PoetryTemplate, _make_syl, register


def _tone(t: str) -> dict[str, Any]:
    """Build a tone-only constraint.

    Args:
        t: Tone value ("平" or "仄").

    Returns:
        Constraint dict.

    """
    return _make_syl(attributes={"tone": t})


_FREE: dict[str, Any] = _make_syl()

#: Data-driven structural rules for regulated verse (carried across conversion).
_JINTI_COMMON: dict[str, Any] = {
    "kind": "jinti",
    "attribute": "tone",
    "level_value": "平",
    "oblique_value": "仄",
    "positions": [1, 3],
    "rhyme_lines": [1, 3],
    "optional_first_rhyme": True,
    "forbid_sanpingwei": True,
    "forbid_guping": True,
}
_JINTI_WUJUE: dict[str, Any] = dict(_JINTI_COMMON)
_JINTI_QIJUE: dict[str, Any] = {**_JINTI_COMMON, "positions": [1, 3, 5]}
_JINTI_WULV: dict[str, Any] = {**_JINTI_COMMON, "rhyme_lines": [1, 3, 5, 7]}
_JINTI_QILV: dict[str, Any] = {
    **_JINTI_COMMON,
    "positions": [1, 3, 5],
    "rhyme_lines": [1, 3, 5, 7],
}


#: Xiangjianhuan default punctuation (7 lines: , . . , , . .).
_XIANGJIANHUAN_MARKS: list[str] = ["，", "。", "。", "，", "，", "。", "。"]

#: Rumengling default punctuation (7 lines).
_RUMENGLING_MARKS: list[str] = ["，", "。", "，", "。", "，", "，", "。"]

#: Langtaosha default punctuation (5 lines per stanza).
_LANGTAOSHA_MARKS: list[str] = ["，", "。", "。", "，", "。"] * 2

#: Qingpingyue default punctuation (4 lines per stanza).
_QINGPINGYUE_MARKS: list[str] = ["，", "。", "，", "。", "，", "。", "，", "。"]

#: Xijiangyue default punctuation (4 lines per stanza; rhyme lines 2-4 end
#: with full stops).
_XIJIANGYUE_MARKS: list[str] = ["，", "。", "。", "。"] * 2

#: Busuanzi default punctuation (4 lines per stanza).
_BUSUANZI_MARKS: list[str] = ["，", "。", "，", "。"] * 2


def _check_sanpingwei(syllables: list[Syllable]) -> list[str]:
    """Check for a three level-tone tail (last three characters all level).

    Args:
        syllables: Syllables of one line.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    if len(syllables) >= 3:
        last3 = [s.attributes.get("tone", "") for s in syllables[-3:]]
        if last3 == ["平", "平", "平"]:
            errors.append(
                "Three level-tone tail: the last three characters are all "
                "level tones, which violates the meter"
            )
    return errors


def _check_guping(syllables: list[Syllable]) -> list[str]:
    """Check isolated level: a level-ending line with only one level character.

    Isolated level is a major fault in regulated verse: if a level-ending line
    has no second level character besides the rhyme foot, the line is invalid.
    Oblique-ending lines are not checked.

    Args:
        syllables: Syllables of one line.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    if not syllables:
        return errors
    if syllables[-1].attributes.get("tone", "") != "平":
        return errors
    ping_count = sum(1 for s in syllables if s.attributes.get("tone", "") == "平")
    if ping_count == 1:
        errors.append(
            "Isolated level: the level-ending line has only one level tone "
            "(the rhyme foot), which violates the meter"
        )
    return errors


def _check_alternation(syllables: list[Syllable], even_pattern: list[str]) -> list[str]:
    """Check the 2-4-6 rule: even positions must match the given tone pattern.

    Args:
        syllables: Syllables of one line.
        even_pattern: Expected level/oblique tones at even positions.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    n = len(syllables)
    for pos_idx, expected in enumerate(even_pattern):
        actual_pos = pos_idx * 2 + 1
        if actual_pos < n:
            actual_tone = syllables[actual_pos].attributes.get("tone", "")
            if actual_tone and actual_tone != expected:
                errors.append(
                    f"Character {actual_pos + 1} should be {expected} tone "
                    f"(2-4-6 rule) but is {actual_tone}"
                )
    return errors


# *Zhonghua Tongyun* 16 rhyme-group merge (keyed by nucleus + coda; ü is
# stored as v in pypinyin).
# Key correction versus the old 13-rhyme scheme: the "i/ü/er" group differs
# from "u"; the apical vowel -i forms its own "zhi" group.
_TONGYUN: dict[str, str] = {
    "a": "麻",
    "ia": "麻",
    "ua": "麻",
    "o": "波",
    "e": "波",
    "uo": "波",
    "ie": "皆",
    "üe": "皆",
    "ve": "皆",
    "ue": "皆",
    "ai": "开",
    "uai": "开",
    "ei": "微",
    "ui": "微",
    "ao": "豪",
    "iao": "豪",
    "ou": "尤",
    "iu": "尤",
    "an": "寒",
    "ian": "寒",
    "uan": "寒",
    "üan": "寒",
    "van": "寒",
    "en": "文",
    "in": "文",
    "un": "文",
    "ün": "文",
    "vn": "文",
    "ang": "唐",
    "iang": "唐",
    "uang": "唐",
    "eng": "庚",
    "ing": "庚",
    "ueng": "庚",
    "ong": "东",
    "iong": "东",
    "i": "齐",
    "er": "齐",
    "ü": "齐",
    "v": "齐",
    "u": "姑",
}

# Onsets of apical vowels (zhi/chi/shi/ri...): their final -i belongs to the
# "zhi" group rather than the "qi" group.
_APICAL_ONSETS: frozenset[str] = frozenset({"z", "c", "s", "zh", "ch", "sh", "r"})


def _rhyme_key(syl: Syllable) -> str:
    """Build a rhyme key: merge nucleus + coda by *Zhonghua Tongyun*.

    Look up the syllable's nucleus + coda (tone digits already removed) in the
    rhyme-group table. In particular: when the final is "i" and the onset is an
    apical z/c/s/zh/ch/sh/r, it belongs to the "zhi" group; otherwise "i/ü/er"
    belong to "qi" and "u" to "gu" -- "qi" and "gu" are different groups, so
    "i" and "u" do not rhyme. The key values themselves are the Chinese
    rhyme-group names listed in ``_TONGYUN``.

    Args:
        syl: The rhyme-foot syllable.

    Returns:
        Rhyme-group name (one of the ``_TONGYUN`` values); an unknown final
        returns the raw string or "?".

    """
    nucleus = syl.nucleus or ""
    coda = syl.coda or ""
    raw = nucleus + coda
    if raw == "i" and syl.onset in _APICAL_ONSETS:
        return "支"
    if raw in _TONGYUN:
        return _TONGYUN[raw]
    return raw or "?"


def _check_rhyme(
    syllables_list: list[list[Syllable]],
    rhyme_lines: list[int],
    description: str = "Rhyme",
) -> list[str]:
    """Check that the specified lines rhyme (last syllable nucleus + coda).

    Args:
        syllables_list: Syllables per line.
        rhyme_lines: Line numbers participating in the rhyme (0-based).
        description: Error description prefix.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    rhyme_keys: list[tuple[int, str]] = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            rhyme_keys.append((line_idx, _rhyme_key(last)))
    if len(rhyme_keys) < 2:
        return errors
    base_idx, base_rhyme = rhyme_keys[0]
    for line_idx, rhyme in rhyme_keys[1:]:
        if rhyme and rhyme != base_rhyme:
            errors.append(
                f"{description}: line {base_idx + 1} rhymes with "
                f"'{base_rhyme}', line {line_idx + 1} rhymes with '{rhyme}'; "
                f"they do not rhyme"
            )
    return errors


def _check_jinti_rhyme(
    syllables_list: list[list[Syllable]],
    rhyme_lines: list[int],
    description: str = "Rhyme",
) -> list[str]:
    """Check regulated-verse rhyme: even lines use level rhyme; first joins too.

    The first line joins the rhyme when its last character is a level tone.

    Args:
        syllables_list: Syllables per line.
        rhyme_lines: Even line numbers (0-based).
        description: Error description prefix.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    keys: list[tuple[int, str]] = []
    for line_idx in rhyme_lines:
        if line_idx < len(syllables_list) and syllables_list[line_idx]:
            last = syllables_list[line_idx][-1]
            if last.attributes.get("tone", "") != "平":
                errors.append(
                    f"Line {line_idx + 1} rhyme foot should be a level-tone "
                    f"character but is "
                    f"'{last.attributes.get('tone') or 'unknown'}'"
                )
            keys.append((line_idx, _rhyme_key(last)))
    first = syllables_list[0][-1] if syllables_list and syllables_list[0] else None
    if first is not None and first.attributes.get("tone") == "平":
        keys.insert(0, (0, _rhyme_key(first)))
    if len(keys) < 2:
        return errors
    base_idx, base_rhyme = keys[0]
    for line_idx, rhyme in keys[1:]:
        if rhyme and rhyme != base_rhyme:
            errors.append(
                f"{description}: line {base_idx + 1} rhymes with "
                f"'{base_rhyme}', line {line_idx + 1} rhymes with '{rhyme}'; "
                f"they do not rhyme"
            )
    return errors


def _check_jinti_structure(
    syllables_list: list[list[Syllable]],
) -> list[str]:
    """Check regulated-verse line structure: 2/4(6) alternation, opposition, adhesion.

    Leading lines (odd lines from line 3) must end oblique; responding lines
    (even lines) must end level; unknown tone values are skipped.

    Args:
        syllables_list: Syllables per line.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    if len(syllables_list) < 2:
        return errors
    first_len = len(syllables_list[0])
    positions = [1, 3] if first_len <= 5 else [1, 3, 5]

    def line_tones(idx: int) -> list[str]:
        """Get the tones at fixed positions of a line.

        Args:
            idx: Line number.

        Returns:
            Tones at fixed positions (empty string for unknown items).

        """
        syls = syllables_list[idx]
        return [syls[p].attributes.get("tone", "") for p in positions if p < len(syls)]

    prev_couplet_in: list[str] | None = None
    for i in range(0, len(syllables_list) - 1, 2):
        out = line_tones(i)
        in_ = line_tones(i + 1)

        # Leading lines (odd lines from line 3) end oblique; the first line is
        # exempt (it may rhyme with a level ending or end oblique).
        if i >= 2 and syllables_list[i]:
            last_tone = syllables_list[i][-1].attributes.get("tone", "")
            if last_tone == "平":
                errors.append(
                    f"Line {i + 1} is a leading line; its last character "
                    f"should be oblique but is level"
                )
        # Responding lines (even lines) end level.
        if syllables_list[i + 1]:
            last_tone = syllables_list[i + 1][-1].attributes.get("tone", "")
            if last_tone == "仄":
                errors.append(
                    f"Line {i + 2} is a responding line; its last character "
                    f"should be level but is oblique"
                )

        # Alternate tones at positions 2/4(6) of every line.
        for j in range(len(positions) - 1):
            for idx, tones in ((i, out), (i + 1, in_)):
                a = tones[j] if j < len(tones) else ""
                b = tones[j + 1] if j + 1 < len(tones) else ""
                if a and b and a == b:
                    errors.append(
                        f"Line {idx + 1} characters {positions[j] + 1} and "
                        f"{positions[j + 1] + 1} should alternate in tone "
                        f"but are both '{a}'"
                    )

        # Opposition within a couplet.
        for j, (a, b) in enumerate(zip(out, in_)):
            if a and b and a == b:
                errors.append(
                    f"Lines {i + 1} and {i + 2} should oppose: character "
                    f"{positions[j] + 1} should have the opposite tone but "
                    f"both are '{a}'"
                )

        # Adhesion across couplets.
        if prev_couplet_in is not None:
            for j, (a, b) in enumerate(zip(prev_couplet_in, out)):
                if a and b and a != b:
                    errors.append(
                        f"Line {i + 1} should adhere to line {i}: character "
                        f"{positions[j] + 1} should have the same tone but "
                        f"is '{a}' and '{b}'"
                    )

        prev_couplet_in = in_
    return errors


def _check_lv_alternation(
    syllables: list[Syllable], line_idx: int, constraints: list[list[dict[str, Any]]]
) -> list[str]:
    """Check the regulated-poem 2-4-6 rule against constraint-table even positions.

    Args:
        syllables: Syllables of one line.
        line_idx: Line number.
        constraints: Per-position constraint table.

    Returns:
        List of errors.

    """
    errors: list[str] = []
    if line_idx < len(constraints) and len(syllables) >= 3:
        even_pattern: list[str] = []
        for pos in range(1, len(syllables), 2):
            if pos < len(constraints[line_idx]):
                expected = (
                    constraints[line_idx][pos].get("attributes", {}).get("tone", "")
                )
                if expected:
                    even_pattern.append(expected)
        if even_pattern:
            errors.extend(_check_alternation(syllables, even_pattern))
    return errors


def _check_jinti_full(
    syllables: list[list[Syllable]], rhyme_lines: list[int], rhyme_desc: str
) -> list[str]:
    """Full regulated-verse check (shared by five/seven-character forms).

    Checks per-line three-level-tail/isolated-level faults, line structure
    (alternation/opposition/adhesion/line endings), and rhyme.

    Args:
        syllables: Syllables per line.
        rhyme_lines: Even line numbers that must rhyme (0-based).
        rhyme_desc: Error description prefix for rhyme errors.

    Returns:
        List of error messages (empty means pass).

    """
    errors: list[str] = []
    for syls in syllables:
        errors.extend(_check_sanpingwei(syls))
        errors.extend(_check_guping(syls))
    errors.extend(_check_jinti_structure(syllables))
    errors.extend(_check_jinti_rhyme(syllables, rhyme_lines, rhyme_desc))
    return errors


class WujueTemplate(PoetryTemplate):
    """Five-character quatrain: 4 lines of 5 characters.

    Tones are fixed at positions 2/4; even lines rhyme on a level tone.
    """

    name = "Five-Character Quatrain"
    language = "zh"
    lines = 4
    structural_rules = _JINTI_WUJUE
    rhyme_scheme = "-A-A"
    syllables_per_line: ClassVar[list[int]] = [5, 5, 5, 5]
    rule_description = (
        "Rules: characters 2 and 4 of every line alternate in tone; the two "
        "lines of a couplet oppose each other at characters 2 and 4; the first "
        "line of each couplet adheres in tone to the responding line of the "
        "previous couplet at characters 2 and 4; even lines rhyme on a level "
        "tone, and the first line's final character may rhyme (level) or not "
        "(oblique); avoid a three-level-tone tail and isolated level."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed per-position constraints (odd positions are free).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: three-level-tail/isolated-level/structure/rhyme.

        A three-oblique-tone tail is not treated as a fault.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_jinti_full(syllables, [1, 3], "Rhyme (lines 2 and 4)")

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Quatrain layout: one sentence per line.

        Commas separate lines within a couplet; a period closes it.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or ["，", "。", "，", "。"]
        lines = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        text = "\n".join(lines)
        return title + "\n" + text if title else text


class QijueTemplate(PoetryTemplate):
    """Seven-character quatrain: 4 lines of 7 characters.

    Tones are fixed at positions 2/4/6; even lines rhyme on a level tone.
    """

    name = "Seven-Character Quatrain"
    language = "zh"
    lines = 4
    structural_rules = _JINTI_QIJUE
    rhyme_scheme = "-A-A"
    syllables_per_line: ClassVar[list[int]] = [7, 7, 7, 7]
    rule_description = (
        "Rules: characters 2, 4 and 6 of every line alternate in tone; the two "
        "lines of a couplet oppose each other at characters 2, 4 and 6; the "
        "first line of each couplet adheres in tone to the responding line of "
        "the previous couplet at characters 2, 4 and 6; even lines rhyme on a "
        "level tone, and the first line's final character may rhyme (level) "
        "or not (oblique); avoid a three-level-tone tail and isolated level."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed per-position constraints (odd positions are free).

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: three-level-tail/isolated-level/structure/rhyme.

        A three-oblique-tone tail is not treated as a fault.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_jinti_full(syllables, [1, 3], "Rhyme (lines 2 and 4)")

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Quatrain layout: one sentence per line.

        Commas separate lines within a couplet; a period closes it.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or ["，", "。", "，", "。"]
        lines = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        text = "\n".join(lines)
        return title + "\n" + text if title else text


class WulvTemplate(PoetryTemplate):
    """Five-character regulated poem: 8 lines of 5 characters, four couplets.

    Even lines rhyme on a level tone (antithesis is checked by the review AI).
    """

    name = "Five-Character Regulated Verse"
    language = "zh"
    lines = 8
    structural_rules = _JINTI_WULV
    rhyme_scheme = "-A-A-A-A"
    syllables_per_line: ClassVar[list[int]] = [5] * 8
    rule_description = WujueTemplate.rule_description

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: three-level-tail/isolated-level/structure/rhyme.

        A three-oblique-tone tail is not treated as a fault.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_jinti_full(syllables, [1, 3, 5, 7], "Rhyme (lines 2, 4, 6, 8)")

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Regulated-poem layout: one couplet per line.

        Couplets are separated by commas; a period closes the final couplet.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        coupled: list[str] = []
        if punctuation:
            marked = [
                content[i] + (punctuation[i] if i < len(punctuation) else "")
                for i in range(len(content))
            ]
            for i in range(0, len(marked) - 1, 2):
                coupled.append(marked[i] + marked[i + 1])
            if len(marked) % 2 == 1:
                coupled.append(marked[-1])
        else:
            for i in range(0, len(content) - 1, 2):
                coupled.append(f"{content[i]}，{content[i + 1]}")
            if len(content) % 2 == 1:
                coupled.append(content[-1])
            if coupled:
                coupled[-1] = coupled[-1].rstrip("，") + "。"
        lines = "\n".join(coupled)
        return title + "\n" + lines if title else lines


class QilvTemplate(PoetryTemplate):
    """Seven-character regulated poem: 8 lines of 7 characters, four couplets.

    Even lines rhyme on a level tone (antithesis is checked by the review AI).
    """

    name = "Seven-Character Regulated Verse"
    language = "zh"
    lines = 8
    structural_rules = _JINTI_QILV
    rhyme_scheme = "-A-A-A-A"
    syllables_per_line: ClassVar[list[int]] = [7] * 8
    rule_description = QijueTemplate.rule_description

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """No fixed per-position constraints.

        Returns:
            Per-position syllable constraint table.

        """
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Full check: three-level-tail/isolated-level/structure/rhyme.

        A three-oblique-tone tail is not treated as a fault.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_jinti_full(syllables, [1, 3, 5, 7], "Rhyme (lines 2, 4, 6, 8)")

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Regulated-poem layout: one couplet per line.

        Couplets are separated by commas; a period closes the final couplet.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        coupled: list[str] = []
        if punctuation:
            marked = [
                content[i] + (punctuation[i] if i < len(punctuation) else "")
                for i in range(len(content))
            ]
            for i in range(0, len(marked) - 1, 2):
                coupled.append(marked[i] + marked[i + 1])
            if len(marked) % 2 == 1:
                coupled.append(marked[-1])
        else:
            for i in range(0, len(content) - 1, 2):
                coupled.append(f"{content[i]}，{content[i + 1]}")
            if len(content) % 2 == 1:
                coupled.append(content[-1])
            if coupled:
                coupled[-1] = coupled[-1].rstrip("，") + "。"
        lines = "\n".join(coupled)
        return title + "\n" + lines if title else lines


class XiangjianhuanTemplate(PoetryTemplate):
    """Xiangjianhuan (double tune, 36 characters).

    The upper stanza has three level-tone rhymes; the lower stanza first
    changes to two oblique-tone rhymes, then returns to level-tone rhyme.
    """

    name = "Joy of Meeting"
    language = "zh"
    lines = 7
    special_rules = (
        "The lower stanza's level rhyme must return to the upper stanza's rhyme group",
        "The lower stanza's oblique rhyme must differ from the level rhyme group",
        "Both stanzas' final lines should not end in three level tones",
    )
    rhyme_scheme = "AAABBAA"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [6, 3, 9, 3, 3, 3, 9]
    rule_description = (
        "Rules: the upper stanza's 3 lines all rhyme on level tones "
        "(中平中仄平平 / 仄平平 / 中仄中平平仄仄平平); the lower stanza's 4 "
        "lines first change to two oblique-tone rhymes (中中仄 / 中平仄), then "
        "return to a level rhyme (仄平平 / 中仄中平平仄仄平平), and the lower "
        "stanza's level rhyme must be in the same group as the upper "
        "stanza's; the last three characters of the final line in both "
        "stanzas should not all be level."
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _p, _f, _z, _p, _p],
            [_z, _p, _p],
            [_f, _z, _f, _p, _f, _z, _z, _p, _p],
            [_f, _f, _z],
            [_f, _p, _z],
            [_z, _p, _p],
            [_f, _z, _f, _p, _f, _z, _z, _p, _p],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme check: three level rhymes in the upper stanza.

        The lower stanza changes to oblique rhymes and then returns to a level
        rhyme in the same group. Also warns (not a hard rule) that the last
        three characters of both stanzas' final lines (lines 3 and 7) should
        not be all level.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        for line_idx in (2, 6):
            if line_idx < len(syllables) and syllables[line_idx]:
                last3 = [s.attributes.get("tone", "") for s in syllables[line_idx][-3:]]
                if last3 == ["平", "平", "平"]:
                    errors.append(
                        f"Line {line_idx + 1} ends with three level tones; avoid this"
                    )
        errors.extend(_check_rhyme(syllables, [0, 1, 2], "Rhyme (upper stanza, level)"))
        errors.extend(
            _check_rhyme(syllables, [3, 4], "Rhyme (lower stanza, oblique, changed)")
        )
        errors.extend(
            _check_rhyme(syllables, [5, 6], "Rhyme (lower stanza, level, returned)")
        )

        # The lower stanza's level rhyme should return to the upper stanza's
        # level rhyme group; its oblique rhyme must be in a different group.
        def tail(idx: int) -> str:
            """Get the rhyme key of the given line.

            Args:
                idx: Line number.

            Returns:
                Rhyme key string; empty string when there are no syllables.

            """
            if idx < len(syllables) and syllables[idx]:
                return _rhyme_key(syllables[idx][-1])
            return ""

        upper = tail(0)
        lower_ping = tail(5)
        lower_ze = tail(3)
        if upper and lower_ping and upper != lower_ping:
            errors.append(
                f"The lower stanza's level rhyme should return to the upper "
                f"stanza's level rhyme group: upper '{upper}', lower "
                f"'{lower_ping}'"
            )
        if upper and lower_ze and lower_ze == upper:
            errors.append(
                f"The lower stanza's oblique rhyme should be in a different "
                f"group from the level rhyme (rhyme change): both are "
                f"'{lower_ze}'"
            )
        return errors

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Xiangjianhuan layout: leading tab, tab between stanzas, no line breaks.

        Wrapping inside a stanza is handled by CSS.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _XIANGJIANHUAN_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        upper = "".join(content[:3]) if len(content) >= 3 else "".join(content)
        lower = "".join(content[3:]) if len(content) > 3 else ""
        text = "\t" + upper
        if lower:
            text += "\t" + lower
        return title + "\n" + text if title else text


class RumenglingTemplate(PoetryTemplate):
    """Rumengling (single tune, 33 characters).

    Seven lines with five oblique-tone rhymes and one repeated rhyme; lines 5
    and 6 must be an identical refrain.
    """

    name = "Like a Dream"
    language = "zh"
    lines = 7
    special_rules = ("Lines 5 and 6 must be an identical refrain (verbatim)",)
    rhyme_scheme = "AA-AAAA"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [6, 6, 5, 6, 2, 2, 6]
    rule_description = (
        "Rules: a single tune of seven lines, rhyming throughout on oblique "
        "tones (one rhyme from start to finish); lines 5 and 6 are a "
        "two-character refrain and must be exactly identical; tone patterns: "
        "中仄中平中仄 / 中仄中平中仄 / 中仄仄平平 / 中仄中平中仄 / 中仄 / "
        "中仄 / 中仄中平中仄."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _z, _f, _p, _f, _z],
            [_f, _z, _f, _p, _f, _z],
            [_f, _z, _z, _p, _p],
            [_f, _z, _f, _p, _f, _z],
            [_f, _z],
            [_f, _z],
            [_f, _z, _f, _p, _f, _z],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme and refrain check: oblique rhyme throughout; lines 5-6 repeat.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        errors.extend(_check_rhyme(syllables, [0, 1, 3, 4, 5, 6], "Rhyme (oblique)"))
        if len(poem) > 5 and poem[4].strip() and poem[4].strip() != poem[5].strip():
            errors.append(
                f"Lines 5 and 6 should be an identical refrain; got "
                f"'{poem[4]}' and '{poem[5]}'"
            )
        return errors

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Rumengling layout: leading tab, single tune without stanza breaks.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _RUMENGLING_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        text = "\t" + "".join(content)
        return title + "\n" + text if title else text


class LangtaoshaTemplate(PoetryTemplate):
    """Langtaosha (double tune, 54 characters).

    The upper and lower stanzas each have five lines and four level-tone
    rhymes, with a single rhyme throughout.
    """

    name = "Waves Washing the Sand"
    language = "zh"
    lines = 10
    rhyme_scheme = "AAA-AAAA-A"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [5, 4, 7, 7, 4, 5, 4, 7, 7, 4]
    rule_description = (
        "Rules: a double tune of ten lines; the upper and lower stanzas each "
        "have five lines and four level-tone rhymes (lines 4 and 9 do not "
        "rhyme), with one rhyme throughout; tone patterns (the same for both "
        "stanzas): 中仄仄平平 / 中仄平平 / 中平中仄仄平平 / 中仄中平平仄仄 / "
        "中仄平平."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _z, _z, _p, _p],
            [_f, _z, _p, _p],
            [_f, _p, _f, _z, _z, _p, _p],
            [_f, _z, _f, _p, _p, _z, _z],
            [_f, _z, _p, _p],
            [_f, _z, _z, _p, _p],
            [_f, _z, _p, _p],
            [_f, _p, _f, _z, _z, _p, _p],
            [_f, _z, _f, _p, _p, _z, _z],
            [_f, _z, _p, _p],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme check: level rhyme throughout both stanzas (lines 4 and 9 skip).

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_rhyme(
            syllables, [0, 1, 2, 4, 5, 6, 7, 9], "Rhyme (level, throughout)"
        )

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Langtaosha layout: leading tab, tab between stanzas, no line breaks.

        Wrapping inside a stanza is handled by CSS.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _LANGTAOSHA_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        upper = "".join(content[:5])
        lower = "".join(content[5:])
        text = "\t" + upper
        if lower:
            text += "\t" + lower
        return title + "\n" + text if title else text


class QingpingyueTemplate(PoetryTemplate):
    """Qingpingyue (double tune, 46 characters).

    The upper stanza's four lines all carry oblique-tone rhymes; the lower
    stanza rhymes level tones on alternate lines (line 7 does not rhyme), with
    a rhyme change between stanzas.
    """

    name = "Pure Serene Music"
    language = "zh"
    lines = 8
    special_rules = (
        "The stanzas change rhyme; the two rhymes must be in different groups",
    )
    rhyme_scheme = "AAAABB-B"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [4, 5, 7, 6, 6, 6, 6, 6]
    rule_description = (
        "Rules: the upper stanza's four lines each rhyme on oblique tones; "
        "the lower stanza's four lines rhyme on level tones on alternate "
        "lines (line 7 does not rhyme); the two stanzas change rhyme; tone "
        "patterns: upper stanza 中平中仄 / 中仄平平仄 / 中仄中平平仄仄 / "
        "中仄中平中仄, lower stanza 中平中仄平平 / 中平中仄平平 / "
        "中仄中平中仄 / 中平中仄平平."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _p, _f, _z],
            [_f, _z, _p, _p, _z],
            [_f, _z, _f, _p, _p, _z, _z],
            [_f, _z, _f, _p, _f, _z],
            [_f, _p, _f, _z, _p, _p],
            [_f, _p, _f, _z, _p, _p],
            [_f, _z, _f, _p, _f, _z],
            [_f, _p, _f, _z, _p, _p],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme check: oblique rhyme in the upper stanza, level in the lower.

        The two stanzas must change rhyme.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        errors.extend(_check_rhyme(syllables, [0, 1, 2, 3], "Rhyme (upper, oblique)"))
        errors.extend(_check_rhyme(syllables, [4, 5, 7], "Rhyme (lower, level)"))
        upper = _rhyme_key(syllables[0][-1]) if syllables and syllables[0] else ""
        lower = (
            _rhyme_key(syllables[4][-1]) if len(syllables) > 4 and syllables[4] else ""
        )
        if upper and lower and upper == lower:
            errors.append(
                f"The stanzas should change rhyme: upper '{upper}' and lower "
                f"'{lower}' are in the same group"
            )
        return errors

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Qingpingyue layout: leading tab, tab between stanzas, no line breaks.

        Wrapping inside a stanza is handled by CSS.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _QINGPINGYUE_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        upper = "".join(content[:4])
        lower = "".join(content[4:])
        text = "\t" + upper
        if lower:
            text += "\t" + lower
        return title + "\n" + text if title else text


class XijiangyueTemplate(PoetryTemplate):
    """Xijiangyue (double tune, 50 characters).

    The upper and lower stanzas each have four lines. In each stanza, lines 2
    and 3 rhyme on level tones, while line 4 rhymes on an oblique tone in the
    same rhyme group as the level rhyme (level/oblique rhyme alternation). The
    first two lines of each stanza are usually antithetical.
    """

    name = "Moon over the West River"
    language = "zh"
    lines = 8
    special_rules = (
        "The first two lines of each stanza should form an antithetical couplet",
        "The level and oblique rhymes must be in the same rhyme group",
    )
    rhyme_scheme = "-AAB-AAB"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [6, 6, 7, 6, 6, 6, 7, 6]
    rule_description = (
        "Rules: a double tune of 50 characters, four lines per stanza, eight "
        "lines in total; in each stanza lines 2 and 3 rhyme on level tones and "
        "line 4 rhymes on an oblique tone, and the oblique rhyme must be in "
        "the same rhyme group as the level rhyme (level/oblique rhyme "
        "alternation); the first two lines of each stanza are usually "
        "antithetical; tone patterns for both stanzas: 中仄中平平仄 / "
        "中平中仄平平 / 中平中仄仄平平 / 中仄平平中仄."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _z, _f, _p, _p, _z],
            [_f, _p, _f, _z, _p, _p],
            [_f, _p, _f, _z, _z, _p, _p],
            [_f, _z, _p, _p, _f, _z],
            [_f, _z, _f, _p, _p, _z],
            [_f, _p, _f, _z, _p, _p],
            [_f, _p, _f, _z, _z, _p, _p],
            [_f, _z, _p, _p, _f, _z],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme check: level rhymes in lines 2-3 and an oblique rhyme in line 4.

        The level and oblique rhymes must belong to the same rhyme group.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        errors: list[str] = []
        errors.extend(_check_rhyme(syllables, [1, 2, 5, 6], "Rhyme (level)"))
        errors.extend(_check_rhyme(syllables, [3, 7], "Rhyme (oblique)"))

        def tail(idx: int) -> str:
            """Get the rhyme key of the final syllable of one line.

            Args:
                idx: Line number (0-based).

            Returns:
                Rhyme key string; empty when the line has no syllables.

            """
            if idx < len(syllables) and syllables[idx]:
                return _rhyme_key(syllables[idx][-1])
            return ""

        level = tail(1) or tail(2)
        oblique = tail(3) or tail(7)
        if level and oblique and level != oblique:
            errors.append(
                f"The level and oblique rhymes must be in the same rhyme "
                f"group: level '{level}', oblique '{oblique}'"
            )
        return errors

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Xijiangyue layout: leading tab, tab between stanzas, no breaks.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _XIJIANGYUE_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        upper = "".join(content[:4])
        lower = "".join(content[4:])
        text = "\t" + upper
        if lower:
            text += "\t" + lower
        return title + "\n" + text if title else text


class BusuanziTemplate(PoetryTemplate):
    """Busuanzi (double tune, 44 characters).

    Four lines per stanza; lines 2 and 4 of each stanza rhyme throughout on
    oblique tones.
    """

    name = "Song of Divination"
    language = "zh"
    lines = 8
    special_rules = ("All rhymes use oblique tones",)
    rhyme_scheme = "-A-A-A-A"
    centered = False
    syllables_per_line: ClassVar[list[int]] = [5, 5, 7, 5, 5, 5, 7, 5]
    rule_description = (
        "Rules: a double tune of 44 characters, four lines per stanza, eight "
        "lines in total; lines 2 and 4 of each stanza rhyme throughout on "
        "oblique tones; tone patterns for both stanzas: 中仄仄平平 / "
        "中仄平平仄 / 中仄平平仄仄平 / 中仄平平仄."
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """Fixed tone pattern of the ci tune (free positions are unconstrained).

        Returns:
            Per-position syllable constraint table.

        """
        _f, _p, _z = _FREE, _tone("平"), _tone("仄")
        return [
            [_f, _z, _z, _p, _p],
            [_f, _z, _p, _p, _z],
            [_f, _z, _p, _p, _z, _z, _p],
            [_f, _z, _p, _p, _z],
            [_f, _z, _z, _p, _p],
            [_f, _z, _p, _p, _z],
            [_f, _z, _p, _p, _z, _z, _p],
            [_f, _z, _p, _p, _z],
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """Rhyme check: lines 2 and 4 of each stanza rhyme on oblique tones.

        Args:
            poem: List of poem lines.
            syllables: Syllables per line.

        Returns:
            List of error messages (empty means pass).

        """
        return _check_rhyme(syllables, [1, 3, 5, 7], "Rhyme (oblique)")

    def format_poem(self, poem: list[str], punctuation: list[str] | None = None) -> str:
        """Busuanzi layout: leading tab, tab between stanzas, no breaks.

        Args:
            poem: List of poem lines (first element is the title).
            punctuation: Per-line punctuation; empty/None uses defaults.

        Returns:
            Formatted display text.

        """
        title = poem[0] if poem else ""
        content = poem[1:] if len(poem) > 1 else poem
        marks = punctuation or _BUSUANZI_MARKS
        content = [
            content[i] + (marks[i] if i < len(marks) else "")
            for i in range(len(content))
        ]
        upper = "".join(content[:4])
        lower = "".join(content[4:])
        text = "\t" + upper
        if lower:
            text += "\t" + lower
        return title + "\n" + text if title else text


def register_chinese_templates() -> None:
    """Register all Chinese templates."""
    register("zh_wujue", WujueTemplate())
    register("zh_qijue", QijueTemplate())
    register("zh_wulv", WulvTemplate())
    register("zh_qilv", QilvTemplate())
    register("zh_xiangjianhuan", XiangjianhuanTemplate())
    register("zh_rumengling", RumenglingTemplate())
    register("zh_langtaosha", LangtaoshaTemplate())
    register("zh_qingpingyue", QingpingyueTemplate())
    register("zh_xijiangyue", XijiangyueTemplate())
    register("zh_busuanzi", BusuanziTemplate())
