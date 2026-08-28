# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""拉丁语格律模板：六步格、哀歌双行体、十一音节诗。

- 六步格：第 1-4 音步扬抑抑/扬扬自由替换，第 5 音步必须扬抑抑格，
  第 6 音步 2 音节（扬扬或扬抑）。
- 哀歌双行体：第 1 行六步格，第 2 行五步格（后 6 音节必须两个完整扬抑抑格）。
- 十一音节诗：第 1 音步首音节必长，第 5/6 音节之间必须是词边界。
"""

from typing import Any, ClassVar

from ..models.syllable import Syllable
from ..prosody.latin import LatinAnalyzer
from . import ConstraintTable, PoetryTemplate, register

_LATIN = LatinAnalyzer()


def _make_syl(**kwargs: Any) -> dict[str, Any]:
    """构造逐位约束字典。

    Args:
        **kwargs: 可含 onset/nucleus/coda 及 attributes。

    Returns:
        约束字典。
    """
    attrs = kwargs.pop("attributes", {})
    if not isinstance(attrs, dict):
        attrs = {}
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


_L: dict[str, Any] = _make_syl(attributes={"length": "long"})
_S: dict[str, Any] = _make_syl(attributes={"length": "short"})


def _validate_hex(syls: list[Syllable]) -> list[str]:
    """六步格完整校验。

    第 1-4 音步为扬抑抑格(长短短)或扬扬格(长长)自由替换；
    第 5 音步必须为扬抑抑格（长短短）；第 6 音步为扬扬格或扬抑格（2 音节）。

    Args:
        syls: 一行音节。

    Returns:
        错误列表。
    """
    errors: list[str] = []
    n = len(syls)
    if n < 13:
        errors.append(f"音节数不足: 至少13个，实际{n}个")
        return errors
    i = 0
    feet: list[tuple[int, int, int]] = []
    for foot_idx in range(4):
        if i >= n:
            break
        if (
            i + 2 < n
            and syls[i + 1].attributes.get("length") == "short"
            and syls[i + 2].attributes.get("length") == "short"
        ):
            feet.append((foot_idx, i, i + 3))
            i += 3
        else:
            feet.append((foot_idx, i, i + 2))
            i += 2
    if i + 3 <= n:
        feet.append((4, i, i + 3))
        i += 3
    else:
        feet.append((4, i, n))
        i = n
    if i < n:
        feet.append((5, i, n))

    if len(feet) < 6:
        errors.append(f"音步不足: 需要6个音步，实际扫描出{len(feet)}个")
        return errors

    for foot_idx, start, end in feet:
        foot = syls[start:end]
        first_len = foot[0].attributes.get("length", "")
        if foot_idx < 4:
            if first_len != "long":
                errors.append(
                    f"第{foot_idx + 1}音步应以长音节开头，实际为{first_len or '未知'}"
                )
            if len(foot) == 3:
                if (
                    foot[1].attributes.get("length") != "short"
                    or foot[2].attributes.get("length") != "short"
                ):
                    errors.append(f"第{foot_idx + 1}音步扬抑抑格应为长短短，实际不满足")
            elif len(foot) == 2 and foot[1].attributes.get("length") != "long":
                errors.append(
                    f"第{foot_idx + 1}音步扬扬格应两个长音节，实际第二个为{foot[1].attributes.get('length') or '未知'}"
                )
        elif foot_idx == 4:
            if len(foot) != 3:
                errors.append(f"第5音步必须为扬抑抑格（3音节），实际{len(foot)}个")
            elif (
                first_len != "long"
                or foot[1].attributes.get("length") != "short"
                or foot[2].attributes.get("length") != "short"
            ):
                errors.append("第5音步必须为扬抑抑格（长短短），实际不满足")
        else:
            if len(foot) != 2:
                errors.append(f"第6音步应为2音节（扬扬格或扬抑格），实际{len(foot)}个")
            elif first_len != "long":
                errors.append(f"第6音步应以长音节开头，实际为{first_len or '未知'}")
    return errors


class HexameterTemplate(PoetryTemplate):
    """六步格：单行，可连续堆叠，逐行校验。"""

    name = "六步格"
    language = "la"
    lines = 1
    syllables_per_line: ClassVar[list[tuple[int, int]]] = [(13, 17)]
    rule_description = (
        "格律规则：共6音步；第1-4音步可为扬抑抑格(长短短)或扬扬格(长长)自由替换；"
        "第5音步必须为扬抑抑格(长短短)；第6音步为扬扬格或扬抑格，末音节可长可短；"
        "音长判定：词典标注优先，无标注时双元音及元音后跟两个及以上辅音(含跨词)为长音。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无固定位置约束（音步可替换，由 validate_full 贪心扫描）。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """逐音步校验六步格结构。"""
        errors: list[str] = []
        if syllables and syllables[0]:
            errors.extend(_validate_hex(syllables[0]))
        return errors


class DistichonTemplate(PoetryTemplate):
    """哀歌双行体：第 1 行六步格，第 2 行五步格（末 6 音节两完整扬抑抑格）。"""

    name = "哀歌双行体"
    language = "la"
    lines = 2
    syllables_per_line: ClassVar[list[tuple[int, int]]] = [(13, 17), (11, 13)]
    rule_description = (
        "格律规则：第1行完全遵循六步格规则；"
        "第2行五步格：前2.5音步可为扬抑抑格或扬扬格（自由），中间必有停顿，"
        "后2.5音步必须为两个完整的扬抑抑格（长短短长短短）收尾；"
        "两行末字必须押韵（AA）。"
    )

    def get_syllable_constraints(self) -> ConstraintTable | None:
        """无固定位置约束（同六步格）。"""
        return None

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：第 1 行六步格、第 2 行末 6 音节扬抑抑×2、AA 押韵。"""
        errors: list[str] = []
        if not syllables or len(syllables) < 2:
            return errors
        if syllables[0]:
            errors.extend(_validate_hex(syllables[0]))
        pent_syls = syllables[1]
        if len(pent_syls) >= 6:
            tail = pent_syls[-6:]
            expected = ["long", "short", "short", "long", "short", "short"]
            for j, (s, exp) in enumerate(zip(tail, expected)):
                actual = s.attributes.get("length", "")
                if actual and actual != exp:
                    errors.append(
                        f"第2行倒数第{6 - j}音节应为{exp}（后2.5音步须为两个完整扬抑抑格），实际为{actual}"
                    )
        elif len(pent_syls) >= 2:
            errors.append("第2行音节数不足: 至少11个")
        if len(poem) >= 2 and syllables[0] and syllables[1]:
            r0 = syllables[0][-1].nucleus + syllables[0][-1].coda
            r1 = syllables[1][-1].nucleus + syllables[1][-1].coda
            if r0 and r1 and r0 != r1:
                errors.append(f"押韵不匹配: 第1行韵脚为'{r0}'，第2行韵脚为'{r1}'")
        return errors


class HendecasyllabusTemplate(PoetryTemplate):
    """十一音节诗：5 音步，第 5/6 音节间须为词边界。"""

    name = "十一音节诗"
    language = "la"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [11]
    rule_description = (
        "格律规则：共5音步11音节；第1音步为扬扬格或扬抑格（首音节必长）；"
        "第2音步固定扬抑抑格(长短短)；第3-5音步均为扬抑格(长短)；"
        "全行第5与第6音节之间必须是音步边界（不得跨词）；"
        "第3、6、8、10音节（全行）必须为长音。"
    )

    def get_syllable_constraints(self) -> ConstraintTable:
        """固定音步模式约束（第1音步首音节必长）。"""
        return [
            [
                _L,
                {},
                _L,
                _S,
                _S,
                _L,
                _S,
                _L,
                _S,
                _L,
                _S,
            ]
        ]

    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]:
        """完整检查：固定长音位 + 第 5/6 音节间词边界。"""
        errors: list[str] = []
        if not syllables or not syllables[0]:
            return errors
        syls = syllables[0]
        if len(syls) < 11:
            errors.append(f"音节数不足: 需要11个，实际{len(syls)}个")
        patterns = [
            (2, "long"),
            (5, "long"),
            (7, "long"),
            (9, "long"),
        ]
        for pos, expected in patterns:
            if pos < len(syls):
                actual = syls[pos].attributes.get("length", "")
                if actual and actual != expected:
                    errors.append(f"第{pos + 1}音节应为长音节，实际为{actual}")

        if poem:
            line = poem[0]
            cum = 0
            boundary_ok = False
            for w in line.split():
                w_clean = w.strip(".,;:!?\"'()[]{}")
                if not w_clean:
                    continue
                n = len(_LATIN.analyze_word(w_clean))
                if n == 0:
                    continue
                if cum + n == 5:
                    boundary_ok = True
                    break
                cum += n
            if not boundary_ok:
                errors.append("第5与第6音节之间必须是音步边界（词边界），当前边界缺失")
        return errors


def register_latin_templates() -> None:
    """注册全部拉丁语模板。"""
    register("la_hexameter", HexameterTemplate())
    register("la_distichon", DistichonTemplate())
    register("la_hendecasyllabus", HendecasyllabusTemplate())
