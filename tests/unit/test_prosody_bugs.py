# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Discriminating tests for A/B-class correctness bugs in the prosody engine.

These tests describe the behavior that **should** hold. While the code has a
known bug, the corresponding test **fails**, providing continuous regression
protection until the fix lands.

Run with:
    python -m pytest tests/unit/test_prosody_bugs.py -v

Each failing test = one known bug; after the fix it should pass.
"""

from src.models.syllable import Syllable
from src.prosody.chinese import ChineseAnalyzer
from src.prosody.french import _NASAL_FRONT, FrenchAnalyzer
from src.prosody.italian import ItalianAnalyzer
from src.prosody.latin import LatinAnalyzer
from src.templates.zh import _TONGYUN, _check_guping, _rhyme_key

# ====================================================================
# A1: wrong condition for detecting a lone level tone (guping)
# ====================================================================


class TestGupingDetection:
    """A1: _check_guping correctly detects guping (a lone level tone).

    Definition (level-foot line): a line is guping when only the rhyme
    syllable is level tone (ping_count == 1).
    Oblique-foot lines (final syllable oblique) are not checked for guping.
    """

    def test_guping_detected(self) -> None:
        """A line of 仄仄仄仄平 should be detected as guping (only the rhyme is level)."""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert errors, "The 仄仄仄仄平 pattern should be detected as guping"

    def test_no_guping_two_ping(self) -> None:
        """A line of 仄平仄仄平 should not report guping (it has 2 level tones)."""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert not errors, (
            "The 仄平仄仄平 pattern should not report guping (2 level tones)"
        )

    def test_no_guping_ping_ping_ze_ze_ping(self) -> None:
        """A line of 平平仄仄平 should not report guping (2 non-rhyme level tones)."""
        syls = [
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert not errors, "The 平平仄仄平 pattern should not report guping"

    def test_ze_ju_no_guping_check(self) -> None:
        """Oblique-foot lines are not checked for guping (traditional definition)."""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
        ]
        errors = _check_guping(syls)
        assert not errors, "An oblique-foot line should not be checked for guping"

    def test_six_char_guping(self) -> None:
        """Six-character line: 仄仄仄仄仄平 should be detected as guping."""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert errors, "The 仄仄仄仄仄平 pattern should be detected as guping"


# ====================================================================
# A2: ue is not registered in _TONGYUN -> the rhyme key of 月 cannot be assigned
# ====================================================================


class TestUeNotInTongyun:
    """A2: pypinyin emits 'ue4' for 月, so _split_final yields nucleus='ue'.

    But _TONGYUN only contains "üe" and "ve", not "ue".
    Therefore _rhyme_key("月") returns the raw string "ue" instead of "皆",
    so 月/雪/绝 cannot be correctly assigned to the 皆 rhyme group.
    """

    def test_ue_in_tongyun(self) -> None:
        """_TONGYUN should contain the 'ue' key (pypinyin output format)."""
        assert "ue" in _TONGYUN, (
            "_TONGYUN is missing the 'ue' key, so pypinyin output for 月/雪/绝 "
            "cannot be assigned to a rhyme group"
        )

    def test_yue_rhyme_key_is_jie(self) -> None:
        """The rhyme key of 月 should be '皆' (assigned through ue)."""
        a = ChineseAnalyzer()
        syls = a.analyze_word("月")
        assert syls
        rk = _rhyme_key(syls[0])
        assert rk == "皆", f"The rhyme key of 月 should be '皆', got {rk!r}"

    def test_yue_and_xue_rhyme(self) -> None:
        """月 (ue) and 雪 (ue) should rhyme (both 皆)."""
        a = ChineseAnalyzer()
        syls_yue = a.analyze_word("月")
        syls_xue = a.analyze_word("雪")
        assert syls_yue and syls_xue
        assert _rhyme_key(syls_yue[0]) == _rhyme_key(syls_xue[0]), (
            f"月/雪 should rhyme, got {_rhyme_key(syls_yue[0])!r} "
            f"!= {_rhyme_key(syls_xue[0])!r}"
        )


# ====================================================================
# A3: ong/iong should belong to 东, not 庚
# ====================================================================


class TestOngShouldBeDong:
    """A3: in 中华通韵, ong/iong belong to 东 while eng/ing belong to 庚.

    Currently _TONGYUN maps ong/iong to "庚", so 风 (eng) and 中 (ong)
    are judged as rhyming even though 东 and 庚 do not rhyme.
    """

    def test_ong_maps_to_dong(self) -> None:
        """Ong should map to '东', not '庚'."""
        assert _TONGYUN.get("ong") == "东", (
            "_TONGYUN['ong'] should be '东', got {!r}".format(_TONGYUN.get("ong"))
        )

    def test_iong_maps_to_dong(self) -> None:
        """Iong should map to '东', not '庚'."""
        assert _TONGYUN.get("iong") == "东", (
            "_TONGYUN['iong'] should be '东', got {!r}".format(_TONGYUN.get("iong"))
        )

    def test_eng_maps_to_geng(self) -> None:
        """Eng should map to '庚'."""
        assert _TONGYUN.get("eng") == "庚"

    def test_feng_and_zhong_different_rhyme(self) -> None:
        """风 (eng->庚) and 中 (ong->东) should not rhyme."""
        a = ChineseAnalyzer()
        syls_feng = a.analyze_word("风")
        syls_zhong = a.analyze_word("中")
        assert syls_feng and syls_zhong
        rk_feng = _rhyme_key(syls_feng[0])
        rk_zhong = _rhyme_key(syls_zhong[0])
        assert rk_feng != rk_zhong, (
            f"风(庚) and 中(东) should not rhyme, both got {rk_feng!r}"
        )


# ====================================================================
# B2: French nasal vowels am/em/im/um are missing from the merge set
# ====================================================================


class TestFrenchNasalMapping:
    """B2: _NASAL_FRONT is missing am/em/im/um.

    _FR_DIGRAPHS contains am/em/im/um, which are recognized as nuclei like
    diphthongs. But _normalize_nucleus only consults _NASAL_FRONT and
    _NASAL_BACK, and am/em/im/um are in neither, so normalization fails:
    - temps (em) -> rhyme_key='em' instead of 'an'
    - it cannot rhyme with pendant (an)
    """

    def test_am_in_nasal_front(self) -> None:
        """Am should be in _NASAL_FRONT (front nasal)."""
        assert "am" in _NASAL_FRONT, "_NASAL_FRONT is missing 'am'"

    def test_em_in_nasal_front(self) -> None:
        """Em should be in _NASAL_FRONT (front nasal)."""
        assert "em" in _NASAL_FRONT, "_NASAL_FRONT is missing 'em'"

    def test_im_in_nasal_front(self) -> None:
        """Im should be in _NASAL_FRONT (front nasal)."""
        assert "im" in _NASAL_FRONT, "_NASAL_FRONT is missing 'im'"

    def test_um_in_nasal_front(self) -> None:
        """Um should be in _NASAL_FRONT (front nasal)."""
        assert "um" in _NASAL_FRONT, "_NASAL_FRONT is missing 'um'"

    def test_temps_and_pendant_rhyme(self) -> None:
        """Temps (em) and pendant (an) should rhyme (both front nasal)."""
        fr = FrenchAnalyzer()
        rk_temps = fr.rhyme_key("temps")
        rk_pendant = fr.rhyme_key("pendant")
        assert rk_temps == rk_pendant, (
            f"temps and pendant should rhyme, got {rk_temps!r} != {rk_pendant!r}"
        )

    def test_am_and_an_rhyme(self) -> None:
        """Am and an should rhyme (both front nasal -> 'an')."""
        fr = FrenchAnalyzer()
        rk_am = fr.rhyme_key("am")
        rk_an = fr.rhyme_key("an")
        assert rk_am == rk_an, f"am and an should rhyme, got {rk_am!r} != {rk_an!r}"


# ====================================================================
# B3: Latin MCL onset splitting error
# ====================================================================


class TestLatinMclOnset:
    """B3: the MCL syllable split of patris gives onset='ptr'.

    The correct split is pa-tris: onset='p', nucleus='a' | onset='tr',
    nucleus='i', coda='s'. The current algorithm puts the whole consonant
    cluster into the first syllable's onset, producing a wrong structure.
    """

    def test_patris_onset(self) -> None:
        """Patris should have first-syllable onset 'p', not 'ptr'."""
        la = LatinAnalyzer()
        syls = la.analyze_word("patris")
        assert len(syls) == 2
        assert syls[0].onset == "p", (
            f"patris first-syllable onset should be 'p', got {syls[0].onset!r}"
        )

    def test_patris_second_onset(self) -> None:
        """Patris should have second-syllable onset 'tr'."""
        la = LatinAnalyzer()
        syls = la.analyze_word("patris")
        assert len(syls) == 2
        assert syls[1].onset == "tr", (
            f"patris second-syllable onset should be 'tr', got {syls[1].onset!r}"
        )

    def test_stellae_split(self) -> None:
        """stellae: ste-llae (the double consonant ll goes to the next onset)."""
        la = LatinAnalyzer()
        syls = la.analyze_word("stellae")
        assert len(syls) == 2
        assert syls[0].onset == "st", (
            f"stellae first-syllable onset should be 'st', got {syls[0].onset!r}"
        )
        assert syls[1].onset == "ll", (
            f"stellae second-syllable onset should be 'll', got {syls[1].onset!r}"
        )


# ====================================================================
# B4: Latin double consonant ff splitting
# ====================================================================


class TestLatinDoubleConsonant:
    """B4: how the double consonant ff is split affects syllable structure.

    effugit: e-ffu-git = 3 syllables; the double consonant ff belongs as a
    whole to the next syllable's onset.
    """

    def test_effugit_three_syllables(self) -> None:
        """Effugit should have 3 syllables."""
        la = LatinAnalyzer()
        assert la.count_syllables("effugit") == 3

    def test_effugit_second_onset(self) -> None:
        """Effugit's second-syllable onset should be 'ff' (the geminate moves next)."""
        la = LatinAnalyzer()
        syls = la.analyze_word("effugit")
        assert syls[1].onset == "ff", (
            f"effugit second-syllable onset should be 'ff', got {syls[1].onset!r}"
        )


# ====================================================================
# B6: Italian qu cluster handling
# ====================================================================


class TestItalianQuDiphthong:
    """B6: Italian qu should be a consonant onset (kw), not merge into a nucleus.

    The current code gives qui onset='' nucleus='ui', i.e. qu is treated as
    part of the vowel nucleus. It should be onset='qu' nucleus='i' (or
    onset='k' nucleus='wi').
    """

    def test_qui_syllable_count(self) -> None:
        """Qui should be 1 syllable (qu is the onset)."""
        it = ItalianAnalyzer()
        assert it.count_syllables("qui") == 1

    def test_qui_onset(self) -> None:
        """Qui's onset should contain 'qu' rather than be empty."""
        it = ItalianAnalyzer()
        syls = it.analyze_word("qui")
        assert len(syls) == 1
        assert syls[0].onset, (
            f"qui onset should not be empty; got onset={syls[0].onset!r} "
            f"nucleus={syls[0].nucleus!r}"
        )

    def test_quota_two_syllables(self) -> None:
        """Quota should be 2 syllables: quo-ta."""
        it = ItalianAnalyzer()
        assert it.count_syllables("quota") == 2

    def test_quota_first_onset(self) -> None:
        """Quota's first-syllable onset should contain 'qu'."""
        it = ItalianAnalyzer()
        syls = it.analyze_word("quota")
        assert len(syls) == 2
        assert syls[0].onset, (
            f"quota first-syllable onset should not be empty, got {syls[0].onset!r}"
        )
