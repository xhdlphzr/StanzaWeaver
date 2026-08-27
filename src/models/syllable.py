"""数据模型：音节（Syllable）。

格律分析的最小单元——声母(onset)、韵腹(nucleus)、韵尾(coda)以及
平仄/重音/长短等音系属性。所有语言的音节分析器统一产出该结构。
"""

from dataclasses import dataclass, field
from typing import Any

TONE_LABEL = str  # "" | "平" | "仄"
STRESS_LABEL = str  # "" | "heavy" | "light"
LENGTH_LABEL = str  # "" | "long" | "short"


@dataclass
class Syllable:
    """一个音节。

    Attributes:
        onset: 声母/辅音首（英文如 "str"，中文如 "zh"）。
        nucleus: 韵腹/元音核心（中文如 "a"、"iao"，英文如 "IY"）。
        coda: 韵尾/尾辅音（中文如 "ng"，英文如 "T"）。
        attributes: 音系属性字典，键为 tone/stress/length。
    """

    onset: str = ""
    nucleus: str = ""
    coda: str = ""
    attributes: dict[str, str] = field(
        default_factory=lambda: {"tone": "", "stress": "", "length": ""}
    )

    @property
    def text(self) -> str:
        """返回音节完整拼写（onset + nucleus + coda）。"""
        return self.onset + self.nucleus + self.coda

    def match_constraint(self, constraint: dict[str, Any]) -> bool:
        """判断本音节是否满足一条逐位约束。

        约束字典可含 onset/nucleus/coda 及 attributes 子字典；
        空字段表示不限。只有显式给出的字段会被比较。

        Args:
            constraint: 约束字典，如 {"onset": "zh", "attributes": {"tone": "平"}}。

        Returns:
            满足全部约束返回 True，否则 False。
        """
        if not constraint:
            return True
        onset_constraint = constraint.get("onset", "")
        nucleus_constraint = constraint.get("nucleus", "")
        coda_constraint = constraint.get("coda", "")
        attr_constraints = constraint.get("attributes", {})
        if not isinstance(attr_constraints, dict):
            attr_constraints = {}

        if onset_constraint and self.onset != onset_constraint:
            return False
        if nucleus_constraint and self.nucleus != nucleus_constraint:
            return False
        if coda_constraint and self.coda != coda_constraint:
            return False
        for attr_key, attr_val in attr_constraints.items():
            if attr_val and self.attributes.get(attr_key, "") != attr_val:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 化的字典。

        Returns:
            {"onset": ..., "nucleus": ..., "coda": ..., "attributes": {...}}。
        """
        return {
            "onset": self.onset,
            "nucleus": self.nucleus,
            "coda": self.coda,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Syllable":
        """从字典重建音节（to_dict 的逆操作）。

        Args:
            d: to_dict() 产生的字典。

        Returns:
            还原后的 Syllable 实例。
        """
        attrs = d.get("attributes", {})
        if not isinstance(attrs, dict):
            attrs = {}
        return cls(
            onset=str(d.get("onset", "")),
            nucleus=str(d.get("nucleus", "")),
            coda=str(d.get("coda", "")),
            attributes={
                "tone": str(attrs.get("tone", "")),
                "stress": str(attrs.get("stress", "")),
                "length": str(attrs.get("length", "")),
            },
        )
