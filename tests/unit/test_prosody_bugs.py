# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""暴露格律引擎中 A/B 类正确性 bug 的判别测试。

这些测试用例描述的是 **应当** 成立的行为；当代码存在已知 bug 时，
对应测试会 **失败**，从而在修复前提供持续的回归保护。

运行方式：
    python -m pytest tests/unit/test_prosody_bugs.py -v

每个失败的测试 = 一个已知 bug；修复后该测试应变为通过。
"""

from src.models.syllable import Syllable
from src.prosody.chinese import ChineseAnalyzer
from src.prosody.french import _NASAL_FRONT, FrenchAnalyzer
from src.prosody.italian import ItalianAnalyzer
from src.prosody.latin import LatinAnalyzer
from src.templates.zh import _TONGYUN, _check_guping, _rhyme_key

# ====================================================================
# A1: 孤平判定条件错误
# ====================================================================


class TestGupingDetection:
    """A1: _check_guping 正确检测孤平。

    定义（平脚句）：全句仅韵脚一个平声字（ping_count == 1）即为孤平。
    仄脚句（尾字仄声）不检孤平。
    """

    def test_guping_detected(self) -> None:
        """仄仄仄仄平 应检出孤平（全句仅韵脚一平）。"""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert errors, "仄仄仄仄平 应检测出孤平"

    def test_no_guping_two_ping(self) -> None:
        """仄平仄仄平 不应报孤平（全句有2个平声）。"""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert not errors, "仄平仄仄平 不应报孤平（有2个平声）"

    def test_no_guping_ping_ping_ze_ze_ping(self) -> None:
        """平平仄仄平 不应报孤平（非韵脚平声=2）。"""
        syls = [
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert not errors, "平平仄仄平 不应报孤平"

    def test_ze_ju_no_guping_check(self) -> None:
        """仄脚句不检查孤平（传统定义）。"""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
        ]
        errors = _check_guping(syls)
        assert not errors, "仄脚句不应检查孤平"

    def test_six_char_guping(self) -> None:
        """六言孤平：仄仄仄仄仄平 应检出。"""
        syls = [
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "仄"}),
            Syllable(attributes={"tone": "平"}),
        ]
        errors = _check_guping(syls)
        assert errors, "仄仄仄仄仄平 应检测出孤平"


# ====================================================================
# A2: ue 未在 _TONGYUN 中注册 -> 月 的韵脚 key 无法归部
# ====================================================================


class TestUeNotInTongyun:
    """A2: pypinyin 对"月"输出 'ue4'，_split_final 得 nucleus='ue'。

    但 _TONGYUN 中只有 "ue" 和 "ve"，没有 "ue"。
    因此 _rhyme_key("月") 返回原始串 "ue" 而非 "皆"。
    这导致 月/雪/绝 等字无法正确归入皆韵。
    """

    def test_ue_in_tongyun(self) -> None:
        """_TONGYUN 应包含 'ue' 键（pypinyin 输出格式）。"""
        assert "ue" in _TONGYUN, (
            "_TONGYUN 缺少 'ue' 键，pypinyin 输出的月/雪/绝 等字无法归韵"
        )

    def test_yue_rhyme_key_is_jie(self) -> None:
        """月 的韵脚 key 应为 '皆'（通过 ue 归部）。"""
        a = ChineseAnalyzer()
        syls = a.analyze_word("月")
        assert syls
        rk = _rhyme_key(syls[0])
        assert rk == "皆", f"月 的韵脚 key 应为 '皆'，实际为 {rk!r}"

    def test_yue_and_xue_rhyme(self) -> None:
        """月(ue) 和 雪(ue) 应同韵（皆韵）。"""
        a = ChineseAnalyzer()
        syls_yue = a.analyze_word("月")
        syls_xue = a.analyze_word("雪")
        assert syls_yue and syls_xue
        assert _rhyme_key(syls_yue[0]) == _rhyme_key(syls_xue[0]), (
            f"月/雪 应同韵，实际 {_rhyme_key(syls_yue[0])!r} != {_rhyme_key(syls_xue[0])!r}"
        )


# ====================================================================
# A3: ong/iong 应归「东」韵而非「庚」韵
# ====================================================================


class TestOngShouldBeDong:
    """A3: 中华通韵中 ong/iong 属「东」韵，eng/ing 属「庚」韵。

    当前 _TONGYUN 将 ong/iong 映射到 "庚"，导致风(eng)和中(ong)
    被判为同韵，但实际上东/庚不同韵。
    """

    def test_ong_maps_to_dong(self) -> None:
        """ong 应映射到 '东' 而非 '庚'。"""
        assert _TONGYUN.get("ong") == "东", (
            "_TONGYUN['ong'] 应为 '东'，实际为 {!r}".format(_TONGYUN.get("ong"))
        )

    def test_iong_maps_to_dong(self) -> None:
        """iong 应映射到 '东' 而非 '庚'。"""
        assert _TONGYUN.get("iong") == "东", (
            "_TONGYUN['iong'] 应为 '东'，实际为 {!r}".format(_TONGYUN.get("iong"))
        )

    def test_eng_maps_to_geng(self) -> None:
        """eng 应映射到 '庚'。"""
        assert _TONGYUN.get("eng") == "庚"

    def test_feng_and_zhong_different_rhyme(self) -> None:
        """风(eng->庚) 与 中(ong->东) 不应同韵。"""
        a = ChineseAnalyzer()
        syls_feng = a.analyze_word("风")
        syls_zhong = a.analyze_word("中")
        assert syls_feng and syls_zhong
        rk_feng = _rhyme_key(syls_feng[0])
        rk_zhong = _rhyme_key(syls_zhong[0])
        assert rk_feng != rk_zhong, f"风(庚) 与 中(东) 不应同韵，实际均为 {rk_feng!r}"


# ====================================================================
# B2: 法语鼻化元音 am/em/im/um 未纳入归并集合
# ====================================================================


class TestFrenchNasalMapping:
    """B2: _NASAL_FRONT 缺少 am/em/im/um。

    _FR_DIGRAPHS 包含 am/em/im/um，它们作为二合元音被识别为核。
    但 _normalize_nucleus 只查 _NASAL_FRONT 和 _NASAL_BACK，
    am/em/im/um 不在其中，导致归并失败：
    - temps(em) -> rhyme_key='em' 而非 'an'
    - 与 pendant(an) 无法押韵
    """

    def test_am_in_nasal_front(self) -> None:
        """am 应在 _NASAL_FRONT 中（前鼻化）。"""
        assert "am" in _NASAL_FRONT, "_NASAL_FRONT 缺少 'am'"

    def test_em_in_nasal_front(self) -> None:
        """em 应在 _NASAL_FRONT 中（前鼻化）。"""
        assert "em" in _NASAL_FRONT, "_NASAL_FRONT 缺少 'em'"

    def test_im_in_nasal_front(self) -> None:
        """im 应在 _NASAL_FRONT 中（前鼻化）。"""
        assert "im" in _NASAL_FRONT, "_NASAL_FRONT 缺少 'im'"

    def test_um_in_nasal_front(self) -> None:
        """um 应在 _NASAL_FRONT 中（前鼻化）。"""
        assert "um" in _NASAL_FRONT, "_NASAL_FRONT 缺少 'um'"

    def test_temps_and_pendant_rhyme(self) -> None:
        """temps(em) 与 pendant(an) 应同韵（均属前鼻化）。"""
        fr = FrenchAnalyzer()
        rk_temps = fr.rhyme_key("temps")
        rk_pendant = fr.rhyme_key("pendant")
        assert rk_temps == rk_pendant, (
            f"temps 与 pendant 应同韵，实际 {rk_temps!r} != {rk_pendant!r}"
        )

    def test_am_and_an_rhyme(self) -> None:
        """am 与 an 应同韵（均前鼻化 -> 'an'）。"""
        fr = FrenchAnalyzer()
        rk_am = fr.rhyme_key("am")
        rk_an = fr.rhyme_key("an")
        assert rk_am == rk_an, f"am 与 an 应同韵，实际 {rk_am!r} != {rk_an!r}"


# ====================================================================
# B3: 拉丁语 MCL onset 切分错误
# ====================================================================


class TestLatinMclOnset:
    """B3: patris 的 MCL 音节切分结果 onset='ptr'。

    正确切分应为 pa-tris：onset='p', nucleus='a' | onset='tr', nucleus='i', coda='s'。
    当前算法将辅音簇全归入首个音节的 onset，导致音节结构错误。
    """

    def test_patris_onset(self) -> None:
        """patris 的首音节 onset 应为 'p' 而非 'ptr'。"""
        la = LatinAnalyzer()
        syls = la.analyze_word("patris")
        assert len(syls) == 2
        assert syls[0].onset == "p", (
            f"patris 首音节 onset 应为 'p'，实际为 {syls[0].onset!r}"
        )

    def test_patris_second_onset(self) -> None:
        """patris 的第二音节 onset 应为 'tr'。"""
        la = LatinAnalyzer()
        syls = la.analyze_word("patris")
        assert len(syls) == 2
        assert syls[1].onset == "tr", (
            f"patris 第二音节 onset 应为 'tr'，实际为 {syls[1].onset!r}"
        )

    def test_stellae_split(self) -> None:
        """stellae: ste-llae（双辅音 ll 整体属下一音节 onset）。"""
        la = LatinAnalyzer()
        syls = la.analyze_word("stellae")
        assert len(syls) == 2
        assert syls[0].onset == "st", (
            f"stellae 首音节 onset 应为 'st'，实际为 {syls[0].onset!r}"
        )
        assert syls[1].onset == "ll", (
            f"stellae 第二音节 onset 应为 'll'，实际为 {syls[1].onset!r}"
        )


# ====================================================================
# B4: 拉丁语双辅音 ff 切分
# ====================================================================


class TestLatinDoubleConsonant:
    """B4: 双辅音 ff 的切分影响音节结构。

    effugit: e-ffu-git = 3 音节，双辅音 ff 整体属下一音节 onset。
    """

    def test_effugit_three_syllables(self) -> None:
        """effugit 应为 3 音节。"""
        la = LatinAnalyzer()
        assert la.count_syllables("effugit") == 3

    def test_effugit_second_onset(self) -> None:
        """effugit 第二音节 onset 应为 'ff'（双辅音属下一音节）。"""
        la = LatinAnalyzer()
        syls = la.analyze_word("effugit")
        assert syls[1].onset == "ff", (
            f"effugit 第二音节 onset 应为 'ff'，实际为 {syls[1].onset!r}"
        )


# ====================================================================
# B6: 意大利语 qu 双合辅音处理
# ====================================================================


class TestItalianQuDiphthong:
    """B6: 意大利语 qu 应视为辅音 onset（kw），不应与后续元音合并为核。

    当前代码将 qui 的 onset='' nucleus='ui'，即 qu 被当作元音核的一部分。
    正确应为 onset='qu' nucleus='i'（或 onset='k' nucleus='wi'）。
    """

    def test_qui_syllable_count(self) -> None:
        """qui 应为 1 音节（qu 为 onset）。"""
        it = ItalianAnalyzer()
        assert it.count_syllables("qui") == 1

    def test_qui_onset(self) -> None:
        """qui 的 onset 应包含 'qu' 而非为空。"""
        it = ItalianAnalyzer()
        syls = it.analyze_word("qui")
        assert len(syls) == 1
        assert syls[0].onset, (
            f"qui 的 onset 不应为空，实际 onset={syls[0].onset!r} nucleus={syls[0].nucleus!r}"
        )

    def test_quota_two_syllables(self) -> None:
        """quota 应为 2 音节：quo-ta。"""
        it = ItalianAnalyzer()
        assert it.count_syllables("quota") == 2

    def test_quota_first_onset(self) -> None:
        """quota 首音节 onset 应含 'qu'。"""
        it = ItalianAnalyzer()
        syls = it.analyze_word("quota")
        assert len(syls) == 2
        assert syls[0].onset, f"quota 首音节 onset 不应为空，实际 {syls[0].onset!r}"
