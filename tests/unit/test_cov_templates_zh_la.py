# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Supplemental Chinese (zh) / Latin (la) template tests for missing branches.

Only new unit tests are added; no existing test or source file is modified.
The goal is 100% line coverage of ``src/templates/zh.py`` and
``src/templates/la.py`` (the few unreachable dead-code branches are noted
at the end of the file).
"""

from typing import Any

from src.models.syllable import Syllable
from src.templates import _make_syl
from src.templates.la import (
    DistichonTemplate,
    HendecasyllabusTemplate,
    _validate_hex,
)
from src.templates.zh import (
    LangtaoshaTemplate,
    QingpingyueTemplate,
    RumenglingTemplate,
    XiangjianhuanTemplate,
    XijiangyueTemplate,
    _check_alternation,
    _check_guping,
    _check_jinti_rhyme,
    _check_jinti_structure,
    _check_lv_alternation,
    _check_rhyme,
    _rhyme_key,
)


# --------------------------------------------------------------------------- #
# Chinese syllable construction helpers                                                            #
# --------------------------------------------------------------------------- #
def _zs(nucleus: str, coda: str, tone: str) -> Syllable:
    """Build a Chinese syllable (nucleus/coda + tone).

    Args:
        nucleus: Nucleus vowel.
        coda: Coda.
        tone: Tone label ("平"/"仄"/"").

    Returns:
        The constructed Syllable instance.

    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": tone, "stress": "", "length": ""},
    )


def _zline(specs: list[tuple[str, str, str]]) -> list[Syllable]:
    """Build one line of syllables from (nucleus, coda, tone) tuples.

    Args:
        specs: Per-position (nucleus, coda, tone) triples.

    Returns:
        The syllable list for that line.

    """
    return [_zs(n, c, t) for (n, c, t) in specs]


def _ls(nucleus: str, coda: str, length: str) -> Syllable:
    """Build a Latin syllable (nucleus/coda + length).

    Args:
        nucleus: Nucleus vowel.
        coda: Coda.
        length: Length label ("long"/"short"/"").

    Returns:
        The constructed Syllable instance.

    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": "", "stress": "", "length": length},
    )


# --------------------------------------------------------------------------- #
# zh.py: _make_syl / _check_guping / _check_alternation / _rhyme_key          #
# --------------------------------------------------------------------------- #
def test_zh_make_syl_non_dict_attrs() -> None:
    """_make_syl falls back to an empty dict for non-dict attributes (line 29)."""
    result = _make_syl(attributes="not-a-dict")
    assert result["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_zh_check_guping_empty() -> None:
    """An empty line returns immediately without errors (line 88)."""
    assert _check_guping([]) == []


def test_zh_check_alternation_mismatch() -> None:
    """A tone mismatch at an even position is reported (lines 107-117)."""
    syls = [
        _zs("a", "", "仄"),
        _zs("a", "", "平"),
        _zs("a", "", "仄"),
    ]
    errs = _check_alternation(syls, ["仄", "仄", "仄"])
    assert any("2-4-6 rule" in e for e in errs)


def test_zh_rhyme_key_branches() -> None:
    """Apical + i maps to 支; plain finals use the rhyme table (186/188)."""
    assert _rhyme_key(Syllable(onset="zh", nucleus="i", coda="")) == "支"
    assert _rhyme_key(Syllable(onset="", nucleus="a", coda="")) == "麻"


def test_zh_check_rhyme_too_few_keys() -> None:
    """Return early when fewer than two lines participate in rhyme (line 214)."""
    syls = [[_zs("a", "ng", "平")]]
    assert _check_rhyme(syls, [0]) == []


def test_zh_check_jinti_rhyme_ze_foot_and_few_keys() -> None:
    """Report a non-level final on even lines; return early with < 2 rhymes."""
    syls = [
        [_zs("a", "", "仄")],
        [_zs("a", "", "仄")],
    ]
    errs = _check_jinti_rhyme(syls, [1], "Rhyme")
    assert any("rhyme foot should be a level-tone character" in e for e in errs)
    # With only oblique feet and fewer than two rhymes, the oblique-foot error
    # is still reported before the early return (line 255).
    errs2 = _check_jinti_rhyme([[_zs("a", "", "仄")]], [0])
    assert any("rhyme foot should be a level-tone character" in e for e in errs2)


def test_zh_jinti_structure_short_and_feet() -> None:
    """Too few lines returns early; report bad leading and responding feet."""
    assert _check_jinti_structure([[_zs("a", "", "仄")]]) == []
    syls = [
        _zline([("a", "", "仄")] * 5),
        _zline([("a", "", "仄")] * 5),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
            ]
        ),
        _zline([("a", "", "仄")] * 5),
        _zline([("a", "", "仄")] * 5),
    ]
    errs = _check_jinti_structure(syls)
    assert any("leading line" in e for e in errs)
    assert any("responding line" in e for e in errs)


def test_zh_lv_alternation_helper() -> None:
    """Regulated-verse 2-4-6 alternation helper check (lines 356-368)."""
    syls = [
        _zs("a", "", "仄"),
        _zs("a", "", "仄"),
        _zs("a", "", "平"),
        _zs("a", "", "仄"),
        _zs("a", "", "仄"),
    ]
    constraints: list[list[dict[str, Any]]] = [
        [
            _make_syl(),
            _make_syl(attributes={"tone": "平"}),
            _make_syl(),
            _make_syl(attributes={"tone": "仄"}),
            _make_syl(),
        ]
    ]
    errs = _check_lv_alternation(syls, 0, constraints)
    assert isinstance(errs, list)
    assert any("2-4-6 rule" in e for e in errs)


# --------------------------------------------------------------------------- #
# zh.py: Xiangjianhuan validate_full (521/537/538/544/548)                          #
# --------------------------------------------------------------------------- #
def _xjh_mk(n: int, key: str | None, force_ping3: bool = False) -> list[Syllable]:
    """Build one Xiangjianhuan line of syllables.

    Args:
        n: Syllable count of the line.
        key: Final syllable nucleus+coda (None means unconstrained).
        force_ping3: Force the last three syllables level (triggers the
            three-level-tail message).

    Returns:
        The syllable list for that line.

    """
    out: list[Syllable] = []
    for i in range(n):
        if force_ping3 and i >= n - 3:
            out.append(_zs("a", "ng", "平"))
        elif i == n - 1 and key:
            out.append(_zs(key[0], key[1:], ""))
        else:
            out.append(_zs("a", "", ""))
    return out


def test_xjh_last3_ping_and_huan_yun() -> None:
    """Lower stanza: three level tails, level-rhyme return, oblique-rhyme change."""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(9, None, force_ping3=True),
        _xjh_mk(3, "ang"),
        _xjh_mk(3, "eng"),
        _xjh_mk(3, "eng"),
        _xjh_mk(9, "ang"),
    ]
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("ends with three level tones" in e for e in errs)
    assert any("return to the upper stanza" in e for e in errs)
    assert any("rhyme change" in e for e in errs)


def test_xjh_empty_line_tail() -> None:
    """An empty syllable line yields an empty tail (line 538)."""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(9, "ang"),
        _xjh_mk(3, "ang"),
        _xjh_mk(3, "eng"),
        [],
        _xjh_mk(9, "ang"),
    ]
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("rhyme change" in e for e in errs)


# --------------------------------------------------------------------------- #
# zh.py: Rumengling / Langtaosha / Qingpingyue (new ci forms)                  #
# --------------------------------------------------------------------------- #
def test_rumengling_valid_and_constraints() -> None:
    """Rumengling: one oblique rhyme throughout, refrains pass, constraints built."""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(5, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(6, "ang"),
    ]
    poem = ["", "", "", "", "如梦", "如梦", ""]
    tpl = RumenglingTemplate()
    assert tpl.validate_full(poem, syls) == []
    assert len(tpl.get_syllable_constraints()) == 7


def test_rumengling_dieju_mismatch() -> None:
    """Rumengling: report an error when lines 5 and 6 are not identical refrains."""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(5, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(6, "ang"),
    ]
    poem = ["", "", "", "", "如梦", "依旧", ""]
    errs = RumenglingTemplate().validate_full(poem, syls)
    assert any("identical refrain" in e for e in errs)


def test_rumengling_rhyme_mismatch() -> None:
    """Rumengling: report a rhyme error when the rhyme feet differ."""
    syls = [
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "eng"),
        _xjh_mk(5, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(2, "ang"),
        _xjh_mk(6, "ang"),
    ]
    errs = RumenglingTemplate().validate_full([""] * 7, syls)
    assert any("do not rhyme" in e for e in errs)


def test_langtaosha_valid_and_constraints() -> None:
    """Langtaosha: level rhyme throughout both stanzas; constraints built."""
    syls = [
        _xjh_mk(5, "ang"),
        _xjh_mk(4, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(7, None),
        _xjh_mk(4, "ang"),
        _xjh_mk(5, "ang"),
        _xjh_mk(4, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(7, None),
        _xjh_mk(4, "ang"),
    ]
    tpl = LangtaoshaTemplate()
    assert tpl.validate_full([""] * 10, syls) == []
    assert len(tpl.get_syllable_constraints()) == 10


def test_qingpingyue_valid_and_constraints() -> None:
    """Qingpingyue: oblique upper rhyme, level lower rhyme with a change."""
    syls = [
        _xjh_mk(4, "ang"),
        _xjh_mk(5, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "eng"),
        _xjh_mk(6, "eng"),
        _xjh_mk(6, None),
        _xjh_mk(6, "eng"),
    ]
    tpl = QingpingyueTemplate()
    assert tpl.validate_full([""] * 8, syls) == []
    assert len(tpl.get_syllable_constraints()) == 8


def test_qingpingyue_same_rhyme_rejected() -> None:
    """Qingpingyue: report a rhyme change when both stanzas share a group."""
    syls = [
        _xjh_mk(4, "ang"),
        _xjh_mk(5, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
    ]
    errs = QingpingyueTemplate().validate_full([""] * 8, syls)
    assert any("should change rhyme" in e for e in errs)


def test_qingpingyue_empty_syllables() -> None:
    """Qingpingyue: the rhyme foot falls back to empty for empty syllables."""
    assert QingpingyueTemplate().validate_full([], []) == []


def test_xijiangyue_valid_and_constraints() -> None:
    """Xijiangyue: level rhymes plus same-group oblique rhyme; constraints built."""
    syls = [
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "ang"),
    ]
    tpl = XijiangyueTemplate()
    assert tpl.validate_full([""] * 8, syls) == []
    constraints = tpl.get_syllable_constraints()
    assert len(constraints) == 8
    assert [len(row) for row in constraints] == [6, 6, 7, 6, 6, 6, 7, 6]


def test_xijiangyue_rhyme_group_must_match() -> None:
    """Xijiangyue: the oblique rhyme must be in the level rhyme's group."""
    syls = [
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "eng"),
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "eng"),
    ]
    errs = XijiangyueTemplate().validate_full([""] * 8, syls)
    assert any("same rhyme group" in e for e in errs)


def test_xijiangyue_rhyme_mismatch() -> None:
    """Xijiangyue: report level and oblique rhyme mismatches separately."""
    syls = [
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "eng"),
        _xjh_mk(6, "ang"),
        _xjh_mk(6, None),
        _xjh_mk(6, "ang"),
        _xjh_mk(7, "ang"),
        _xjh_mk(6, "eng"),
    ]
    errs = XijiangyueTemplate().validate_full([""] * 8, syls)
    assert any("Rhyme (level)" in e for e in errs)
    assert any("Rhyme (oblique)" in e for e in errs)


def test_xijiangyue_empty_syllables_and_format() -> None:
    """Xijiangyue: empty input and stanza layout."""
    tpl = XijiangyueTemplate()
    assert tpl.validate_full([], []) == []
    text = tpl.format_poem(["题"] + ["句"] * 8)
    assert text.startswith("题\n\t")
    assert "\t" in text
    assert "，" in tpl.format_poem(["题"] + ["句"] * 8, ["，"] * 8)
    assert tpl.format_poem(["题"]) == "题\n\t题，"
    assert not tpl.format_poem(["句"]).startswith("题")


def test_ci_templates_meter_validate_canonical() -> None:
    """Three canonical ci poems pass full MeterValidator checks (positions+rhyme)."""
    from src.prosody.meter_validator import MeterValidator

    validator = MeterValidator()
    cases = [
        (
            RumenglingTemplate(),
            [
                "常记溪亭日暮",
                "沉醉不知归路",
                "兴尽晚回舟",
                "误入藕花深处",
                "争渡",
                "争渡",
                "惊起一滩鸥鹭",
            ],
        ),
        (
            LangtaoshaTemplate(),
            [
                "帘外雨潺潺",
                "春意阑珊",
                "罗衾不耐五更寒",
                "梦里不知身是客",
                "一晌贪欢",
                "独自莫凭栏",
                "无限江山",
                "别时容易见时难",
                "流水落花春去也",
                "天上人间",
            ],
        ),
        (
            QingpingyueTemplate(),
            [
                "别来春半",
                "触目柔肠断",
                "砌下落梅如雪乱",
                "拂了一身还满",
                "雁来音信无凭",
                "路遥归梦难成",
                "离恨恰如春草",
                "更行更远还生",
            ],
        ),
    ]
    for tpl, poem in cases:
        result = validator.validate(poem, tpl.to_dict(), tpl)
        assert result.passed, (tpl.name, result.errors)


def test_rumengling_meter_rejects_bad_rhyme() -> None:
    """MeterValidator rejects a Rumengling whose rhyme feet differ."""
    from src.prosody.meter_validator import MeterValidator

    tpl = RumenglingTemplate()
    poem = [
        "常记溪亭日暮",
        "沉醉不知归路",
        "兴尽晚回舟",
        "误入藕花深处",
        "争渡",
        "争渡",
        "惊起一滩鸥望",
    ]
    result = MeterValidator().validate(poem, tpl.to_dict(), tpl)
    assert result.passed is False
    assert any("do not rhyme" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# la.py: _make_syl / _validate_hex                                            #
# --------------------------------------------------------------------------- #
def test_make_syl_non_dict_attrs() -> None:
    """_make_syl falls back to an empty dict for non-dict attributes (line 32)."""
    result = _make_syl(attributes="nondict")
    assert result["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_la_validate_hex_too_few() -> None:
    """Report and return when fewer than 13 syllables (lines 64-65)."""
    errs = _validate_hex([_ls("a", "", "short") for _ in range(5)])
    assert any("Not enough syllables" in e for e in errs)


def test_la_validate_hex_first_short_and_second_short() -> None:
    """Report non-long first-foot starts and non-long second-foot syllables."""
    syls = [
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
    ]
    errs = _validate_hex(syls)
    assert any("should start with a long syllable" in e for e in errs)
    assert any("spondee should have two long syllables" in e for e in errs)


def test_la_validate_hex_full_scan_valid() -> None:
    """A full 6-foot scan enters the loop with dactyls in the first four feet."""
    syls = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "long"),
    ]
    errs = _validate_hex(syls)
    assert errs == []


def test_la_validate_hex_sixth_foot_first_short() -> None:
    """Report a two-syllable sixth foot whose first syllable is not long."""
    syls: list[Syllable] = []
    for _ in range(4):
        syls.append(_ls("a", "", "long"))
        syls.append(_ls("a", "", "long"))
    syls.append(_ls("a", "", "long"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "short"))
    syls.append(_ls("a", "", "long"))
    errs = _validate_hex(syls)
    assert any("Foot 6 should start with a long syllable" in e for e in errs)


# --------------------------------------------------------------------------- #
# la.py: caesura / Distichon / Hendecasyllabus                                #
# --------------------------------------------------------------------------- #
def test_la_pentameter_caesura_total_small() -> None:
    """Fewer than 6 total syllables is judged as missing a caesura (line 189)."""
    assert DistichonTemplate()._has_pentameter_caesura("arma", 3) is False


def test_la_pentameter_caesura_punct_only() -> None:
    """The word-boundary scan skips punctuation-only words (line 195)."""
    assert DistichonTemplate()._has_pentameter_caesura("...", 6) is False


def test_la_distichon_few_lines() -> None:
    """Return early when there are fewer than two lines (line 210)."""
    assert DistichonTemplate().validate_full(["x"], []) == []


def test_la_distichon_pentameter_too_short() -> None:
    """Report when the pentameter (line 2) has fewer than 6 syllables (228-229)."""
    line0 = [_ls("a", "", "long") for _ in range(13)]
    line1 = [_ls("a", "", "long") for _ in range(4)]
    errs = DistichonTemplate().validate_full(["h", "h"], [line0, line1])
    assert any("Line 2 has too few syllables" in e for e in errs)


def test_la_hendeca_empty() -> None:
    """Return early when there are no syllables (line 276)."""
    assert HendecasyllabusTemplate().validate_full([], []) == []


def test_la_hendeca_too_few() -> None:
    """Report when fewer than 11 syllables (line 279)."""
    line = [_ls("a", "", "long") for _ in range(5)]
    errs = HendecasyllabusTemplate().validate_full(["x"], [line])
    assert any("Not enough syllables" in e for e in errs)


def test_la_hendeca_boundary_punct() -> None:
    """The boundary scan skips punctuation-only words, still missing (line 300)."""
    line = [_ls("a", "", "long") for _ in range(11)]
    errs = HendecasyllabusTemplate().validate_full(["..."], [line])
    assert any("boundary" in e for e in errs)


# --------------------------------------------------------------------------- #
# Unreachable dead-code notes                                                            #
# --------------------------------------------------------------------------- #
# The missing lines below are analyzed as unreachable dead code (even mocking
# cannot trigger them):
#   * zh.py 217, 258: ``_rhyme_key`` always returns a non-empty string
#     (``raw or "?"``), so ``base_rhyme`` is never falsy and the corresponding
#     ``return errors`` branch cannot be entered.
#   * la.py 70: ``_validate_hex`` guarantees n >= 13 before the loop, and each
#     of the first 4 feet consumes at least 2 syllables, so i < n always holds
#     and ``break`` is unreachable.
#   * la.py 107: the 3-syllable feet among the first 4 are created only by the
#     dactyl scan (which requires syls[i+1] and syls[i+2] to be "short"), and
#     they are the same objects read as foot[1]/foot[2] during validation, so
#     the error condition is always false.
#   * la.py 114: entering the foot validation loop (line 94+) requires
#     ``len(feet) >= 6``; a fifth foot exists only as a 3-syllable dactyl
#     (otherwise a sixth foot cannot be formed, and lines 90-92 return early
#     with ``len(feet) < 6``), so the fifth foot's ``len != 3`` branch is
#     unreachable.
#   * la.py 198, 303: ``analyze_word`` always returns >= 1 syllable for a
#     non-empty word, and callers skip an empty ``w_clean`` beforehand, so the
#     ``n == 0`` branch cannot be entered.
