# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Symbol-layer template tests covering validate_full meter rules per language.

The metrical checks of the zh/en/fr/it/la templates lacked direct unit tests;
this file fills the gap: guping, three-level tails, regulated-verse structure
(opposition/cohesion/tone feet), rhyme, and ci rhyme changes; English sonnet /
villanelle / heroic-couplet stress rhyme and refrains; French rondeau /
triolet / ballade refrains and uniform syllables; Italian terza rima /
ottava rima / canzone tenth-syllable stress, chained rhyme and feet; Latin
elegiac-distich pentameter caesura, last-6-syllable length and AA rhyme.
"""

from src.models.syllable import Syllable
from src.templates.en import (
    HeroicCoupletTemplate,
    ShakespeareSonnetTemplate,
    VillanelleTemplate,
)
from src.templates.fr import BalladeTemplate, RondeauTemplate, TrioletTemplate
from src.templates.it import CanzoneTemplate, OttavaRimaTemplate, TerzaRimaTemplate
from src.templates.la import (
    DistichonTemplate,
    HendecasyllabusTemplate,
    HexameterTemplate,
)
from src.templates.zh import (
    QijueTemplate,
    QilvTemplate,
    WujueTemplate,
    WulvTemplate,
    XiangjianhuanTemplate,
    _check_guping,
    _check_sanpingwei,
)


# --------------------------------------------------------------------------- #
# Syllable construction helpers                                                              #
# --------------------------------------------------------------------------- #
def _zs(nucleus: str, coda: str, tone: str) -> Syllable:
    """Build a Chinese syllable (tone + nucleus/coda).

    Args:
        nucleus: Nucleus vowel.
        coda: Coda.
        tone: Tone (level/oblique).

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
        specs: (nucleus, coda, tone) tuple list.

    Returns:
        The Syllable list.

    """
    return [_zs(n, c, t) for (n, c, t) in specs]


def _es(stress: str = "") -> Syllable:
    """Build an English syllable (stress may be 'heavy'/'light'/'').

    Args:
        stress: Stress marker.

    Returns:
        The constructed Syllable instance.

    """
    return Syllable(
        onset="",
        nucleus="a",
        coda="",
        attributes={"tone": "", "stress": stress, "length": ""},
    )


def _en_syls(n_lines: int, n_syl: int = 10) -> list[list[Syllable]]:
    """Build English syllable lines of n_syl syllables with even positions stressed.

    Args:
        n_lines: Line count.
        n_syl: Syllables per line.

    Returns:
        Nested Syllable lists.

    """
    return [
        [_es("heavy" if i % 2 == 0 else "") for i in range(n_syl)]
        for _ in range(n_lines)
    ]


def _is(nucleus: str, coda: str = "", stress: str = "") -> Syllable:
    """Build an Italian syllable (nucleus/coda + stress).

    Args:
        nucleus: Nucleus vowel.
        coda: Coda.
        stress: Stress marker.

    Returns:
        The constructed Syllable instance.

    """
    return Syllable(
        onset="",
        nucleus=nucleus,
        coda=coda,
        attributes={"tone": "", "stress": stress, "length": ""},
    )


def _ls(nucleus: str, coda: str = "", length: str = "") -> Syllable:
    """Build a Latin syllable (nucleus/coda + length).

    Args:
        nucleus: Nucleus vowel.
        coda: Coda.
        length: Length marker.

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
# Chinese: guping / three-level tail (direct units)                                          #
# --------------------------------------------------------------------------- #
def test_check_guping_direct() -> None:
    """Verify direct guping detection."""
    ping_foot_only_one = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    assert _check_guping(ping_foot_only_one)

    ze_foot = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
        ]
    )
    assert _check_guping(ze_foot) == []

    ping_foot_two = _zline(
        [
            ("a", "", "平"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    assert _check_guping(ping_foot_two) == []


def test_check_sanpingwei_direct() -> None:
    """Verify direct three-level-tail detection."""
    san = _zline([("a", "", "平"), ("a", "", "平"), ("a", "", "平")])
    assert _check_sanpingwei(san)
    not_san = _zline([("a", "", "平"), ("a", "", "平"), ("a", "", "仄")])
    assert _check_sanpingwei(not_san) == []


# --------------------------------------------------------------------------- #
# Chinese: five-/seven-character quatrains, valid and violating                                          #
# --------------------------------------------------------------------------- #
def _valid_wujue_syllables() -> list[list[Syllable]]:
    """Valid five-character quatrain syllables.

    Returns:
        4 lines of Syllables.

    """
    return [
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "ng", "平"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "ng", "平"),
            ]
        ),
    ]


def _valid_qijue_syllables() -> list[list[Syllable]]:
    """Valid seven-character quatrain syllables.

    Returns:
        4 lines of Syllables.

    """
    return [
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "ng", "平"),
            ]
        ),
        _zline(
            [
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
            ]
        ),
        _zline(
            [
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "", "平"),
                ("a", "", "平"),
                ("a", "", "仄"),
                ("a", "", "仄"),
                ("a", "ng", "平"),
            ]
        ),
    ]


def test_wujue_valid() -> None:
    """Verify a valid five-character quatrain passes."""
    assert WujueTemplate().validate_full([""] * 4, _valid_wujue_syllables()) == []


def test_wujue_guping_detected() -> None:
    """Verify guping is detected in a five-character quatrain."""
    syls = _valid_wujue_syllables()
    syls[3] = _zline(
        [
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "", "仄"),
            ("a", "ng", "平"),
        ]
    )
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("Isolated level" in e for e in errs)


def test_wujue_sanpingwei_detected() -> None:
    """Verify a three-level tail is detected in a five-character quatrain."""
    syls = _valid_wujue_syllables()
    syls[1] = _zline(
        [
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "", "平"),
            ("a", "ng", "平"),
        ]
    )
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("Three level-tone tail" in e for e in errs)


def test_wujue_rhyme_mismatch() -> None:
    """Verify a five-character quatrain rhyme mismatch."""
    syls = _valid_wujue_syllables()
    syls[3][-1] = _zs("o", "ng", "平")
    errs = WujueTemplate().validate_full([""] * 4, syls)
    assert any("do not rhyme" in e for e in errs)


def test_qijue_valid() -> None:
    """Verify a valid seven-character quatrain passes."""
    assert QijueTemplate().validate_full([""] * 4, _valid_qijue_syllables()) == []


def test_wulv_rhyme_mismatch() -> None:
    """Verify a five-character regulated-verse rhyme mismatch."""
    syls: list[list[Syllable]] = []
    for k in range(8):
        tone = "平" if k % 2 == 1 else "仄"
        coda = "ng" if (k % 2 == 1 and k != 7) else ("ong" if k == 7 else "")
        syls.append([_zs("a", coda, tone) for _ in range(5)])
    errs = WulvTemplate().validate_full([""] * 8, syls)
    assert any("do not rhyme" in e for e in errs)


def test_qilv_sanpingwei_detected() -> None:
    """Verify a three-level tail is detected in a seven-character regulated verse."""
    syls: list[list[Syllable]] = []
    for k in range(8):
        tone = "平" if k % 2 == 1 else "仄"
        syls.append([_zs("a", "", tone) for _ in range(7)])
    syls[1] = [_zs("a", "", "平") for _ in range(7)]
    errs = QilvTemplate().validate_full([""] * 8, syls)
    assert any("Three level-tone tail" in e for e in errs)


# --------------------------------------------------------------------------- #
# Chinese: Xiangjianhuan ci form (rhyme change / level-rhyme return)                                    #
# --------------------------------------------------------------------------- #
def _xjh_syllables() -> list[list[Syllable]]:
    """Valid Xiangjianhuan ci syllables.

    Returns:
        7 lines of Syllables.

    """

    def mk(n: int, key: str | None) -> list[Syllable]:
        """Build a list of n syllables, optionally replacing the final coda.

        Args:
            n: Syllable count.
            key: Rhyme-tail marker (None keeps the default).

        Returns:
            The Syllable list.

        """
        out: list[Syllable] = []
        for i in range(n):
            if i == n - 1 and key:
                out.append(_zs(key[0], key[1:], ""))
            else:
                out.append(_zs("a", "", ""))
        return out

    return [
        mk(6, "ang"),
        mk(3, "ang"),
        mk(9, "ang"),
        mk(3, "eng"),
        mk(3, "eng"),
        mk(3, "ang"),
        mk(9, "ang"),
    ]


def test_xiangjianhuan_valid() -> None:
    """Verify a valid Xiangjianhuan passes."""
    assert XiangjianhuanTemplate().validate_full([""] * 7, _xjh_syllables()) == []


def test_xiangjianhuan_lower_ping_not_returned() -> None:
    """Verify the lower level rhyme not returning to the upper is reported."""
    syls = _xjh_syllables()
    syls[6][-1] = _zs("o", "ng", "")
    errs = XiangjianhuanTemplate().validate_full([""] * 7, syls)
    assert any("return to the upper stanza" in e or "do not rhyme" in e for e in errs)


# --------------------------------------------------------------------------- #
# English: sonnet / villanelle / heroic couplet                                   #
# --------------------------------------------------------------------------- #
def test_sonnet_quatrain_ab_distinct() -> None:
    """Verify sonnet quatrain A/B rhymes must differ."""
    # A-group last line (line 3) and B-group last line (line 4) share a rhyme
    # -> A/B rhymes within one couplet should differ.
    poem = [
        "x light",
        "y night",
        "z light",
        "w night",
        "p day",
        "q time",
        "r fire",
        "s happy",
        "m day",
        "n time",
        "o fire",
        "t happy",
        "u light",
        "v night",
    ]
    syls = _en_syls(14)
    errs = ShakespeareSonnetTemplate().validate_full(poem, syls)
    assert any("A/B" in e for e in errs)


def test_sonnet_rhyme_mismatch() -> None:
    """Verify a sonnet rhyme mismatch is reported."""
    poem = [
        "x light",
        "y love",
        "z cat",
        "w stone",
        "p day",
        "q time",
        "r fire",
        "s happy",
        "m day",
        "n time",
        "o fire",
        "t happy",
        "u light",
        "v night",
    ]
    syls = _en_syls(14)
    errs = ShakespeareSonnetTemplate().validate_full(poem, syls)
    assert any("mismatch" in e for e in errs)


def test_villanelle_refrain_mismatch() -> None:
    """Verify a villanelle refrain mismatch is reported."""
    base = [
        "a light",
        "b love",
        "c night",
        "d stone",
        "e day",
        "f time",
        "g fire",
        "h happy",
        "i night",
        "j stone",
        "k day",
        "l time",
        "m fire",
        "n happy",
        "o night",
        "p stone",
        "q day",
        "r time",
        "s night",
    ]
    poem = list(base)
    poem[5] = "DIFFERENT line"
    poem[11] = "DIFFERENT line"
    poem[17] = "DIFFERENT line"
    syls = _en_syls(19)
    errs = VillanelleTemplate().validate_full(poem, syls)
    assert any("Refrain" in e for e in errs)


def test_heroic_couplet_rhyme() -> None:
    """Verify a heroic couplet rhyme mismatch."""
    poem = ["the light of night", "a song of stone"]
    syls = _en_syls(2)
    errs = HeroicCoupletTemplate().validate_full(poem, syls)
    assert any("mismatch" in e for e in errs)


# --------------------------------------------------------------------------- #
# French: rondeau / triolet / ballade (refrains + uniform syllables)                  #
# --------------------------------------------------------------------------- #
def test_rondeau_refrain_mismatch() -> None:
    """Verify a rondeau refrain mismatch."""
    poem = [
        "premier vers ici mot",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
    ]
    poem[8] = "dernier mot different"
    poem[14] = "dernier mot different"
    t = RondeauTemplate()
    errs = t.validate_full(poem, [[] for _ in range(15)])
    assert any("Refrain" in e for e in errs)


def test_triolet_refrain_mismatch() -> None:
    """Verify a triolet refrain mismatch."""
    poem = [
        "refrain un",
        "refrain deux",
        "trois",
        "quatre",
        "cinq",
        "six",
        "sept",
        "huit",
    ]
    poem[3] = "changed"
    poem[6] = "changed"
    poem[7] = "changed deux"
    errs = TrioletTemplate().validate_full(poem, [[] for _ in range(8)])
    assert any("Refrain" in e for e in errs)


def test_ballade_syllable_uniform_mismatch() -> None:
    """Verify a ballade syllable uniformity mismatch."""
    poem = ["a" for _ in range(28)]
    syls = [[_is("a") for _ in range(8)] for _ in range(28)]
    syls[10] = [_is("a") for _ in range(9)]
    errs = BalladeTemplate().validate_full(poem, syls)
    assert any("syllable count differs" in e for e in errs)


def test_ballade_refrain_mismatch() -> None:
    """Verify a ballade refrain mismatch."""
    poem = ["a" for _ in range(28)]
    syls = [[_is("a") for _ in range(8)] for _ in range(28)]
    poem[15] = "changed refrain"
    poem[23] = "changed refrain"
    poem[27] = "changed refrain"
    errs = BalladeTemplate().validate_full(poem, syls)
    assert any("Refrain" in e for e in errs)


# --------------------------------------------------------------------------- #
# Italian: terza rima / ottava rima / canzone                                        #
# --------------------------------------------------------------------------- #
def test_terzarima_tenth_stress_missing() -> None:
    """Verify a missing tenth-syllable stress in terza rima."""
    line = [_is("a") for _ in range(11)]
    syls = [line for _ in range(14)]
    errs = TerzaRimaTemplate().validate_full([""] * 14, syls)
    assert any("syllable 10" in e for e in errs)


def test_terzarima_rhyme_mismatch() -> None:
    """Verify a terza rima rhyme mismatch."""

    def mk(key: str) -> list[Syllable]:
        """Build an 11-syllable line whose final rhyme tail is key.

        Args:
            key: Rhyme-tail marker.

        Returns:
            The Syllable list.

        """
        out = [_is("a") for _ in range(10)]
        out.append(_is(key))
        return out

    aba = [mk("a"), mk("b"), mk("a")]
    bcb = [mk("b"), mk("c"), mk("b")]
    cdc = [mk("c"), mk("d"), mk("c")]
    ded = [mk("d"), mk("e"), mk("d")]
    ee = [mk("e"), mk("e2"), mk("e")]
    syls = aba + bcb + cdc + ded + ee
    poem = [""] * 14
    errs = TerzaRimaTemplate().validate_full(poem, syls)
    assert any("mismatch" in e for e in errs)


def test_ottava_rima_tenth_stress_ok_rhyme_mismatch() -> None:
    """Verify an ottava rima rhyme mismatch with the tenth stress present."""

    def mk(key: str) -> list[Syllable]:
        """Build an 11-syllable line with the tenth stressed and tail key.

        Args:
            key: Rhyme-tail marker.

        Returns:
            The Syllable list.

        """
        out = [_is("a") for _ in range(10)]
        out[9] = _is("a", "", "heavy")
        out.append(_is(key))
        return out

    lines = [mk("a"), mk("b"), mk("a"), mk("b"), mk("a"), mk("b"), mk("c"), mk("c2")]
    errs = OttavaRimaTemplate().validate_full([""] * 8, lines)
    assert any("mismatch" in e for e in errs)


def test_canzone_constraints() -> None:
    """Verify the canzone constraints."""
    syls: list[list[Syllable]] = []

    def eleven(key: str) -> list[Syllable]:
        """Build an 11-syllable line with the ninth stressed and tail key.

        Args:
            key: Rhyme-tail marker.

        Returns:
            The Syllable list.

        """
        out = [_is("x") for _ in range(11)]
        out[9] = _is("x", "", "heavy")
        out[10] = _is("y")
        out[-1] = _is(key)
        return out

    def seven(key: str) -> list[Syllable]:
        """Build a 7-syllable line whose final rhyme tail is key and stressed.

        Args:
            key: Rhyme-tail marker.

        Returns:
            The Syllable list.

        """
        out = [_is("x") for _ in range(7)]
        out[-1] = _is(key, "", "heavy")
        return out

    for i in range(6):
        syls.append(eleven("a"))
    for i in range(6):
        syls.append(seven("a"))
    syls.append(seven("a"))
    errs = CanzoneTemplate().validate_full([""] * 13, syls)
    assert any("same rhyme three times" in e or "final three lines" in e for e in errs)


# --------------------------------------------------------------------------- #
# Latin: hexameter / elegiac distich / hendecasyllable                              #
# --------------------------------------------------------------------------- #
def test_hexameter_all_short_reports_error() -> None:
    """Verify all-short hexameter reports an error."""
    syls = [_ls("a", "", "short") for _ in range(14)]
    errs = HexameterTemplate().validate_full(["x"], [syls])
    assert errs


def test_distichon_caesura_missing() -> None:
    """Verify a distich missing the pentameter caesura."""
    hexa = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
    ]
    penta = [
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
        _ls("a", "", "long"),
        _ls("a", "", "short"),
        _ls("a", "", "short"),
    ]
    penta[-6:] = [_ls("a", "", "short") for _ in range(6)]
    t = DistichonTemplate()
    errs = t.validate_full(["arma virum", "armavirumquecano"], [hexa, penta])
    assert any("caesura" in e for e in errs)


def test_distichon_rhyme_mismatch() -> None:
    """Verify a distich rhyme mismatch."""
    hexa = [_ls("a", "ng", "long") for _ in range(14)]
    penta = [_ls("a", "ng", "long") for _ in range(12)]
    hexa[-1] = _ls("a", "ng", "long")
    penta[-1] = _ls("o", "ng", "long")
    errs = DistichonTemplate().validate_full(
        ["arma virum", "armavirumquecano"], [hexa, penta]
    )
    assert any("mismatch" in e for e in errs)


def test_hendecasyllabus_boundary_missing() -> None:
    """Verify a hendecasyllable missing the foot boundary."""
    line = [_ls("a", "", "long") for _ in range(11)]
    line[1] = _ls("a", "", "long")
    line[3] = _ls("a", "", "long")
    line[4] = _ls("a", "", "long")
    line[6] = _ls("a", "", "long")
    line[8] = _ls("a", "", "long")
    line[9] = _ls("a", "", "long")
    errs = HendecasyllabusTemplate().validate_full(["aaaaaaaaaaa"], [line])
    assert any("foot boundary" in e for e in errs)


def test_hendecasyllabus_missing_long() -> None:
    """Verify a hendecasyllable missing a long syllable."""
    line = [_ls("a", "", "short") for _ in range(11)]
    errs = HendecasyllabusTemplate().validate_full(["a a a a a a a a a a a"], [line])
    assert any("should be long" in e for e in errs)
