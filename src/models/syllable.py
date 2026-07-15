# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

from dataclasses import dataclass, field


@dataclass
class Syllable:
    onset: str = ""
    nucleus: str = ""
    coda: str = ""
    attributes: dict = field(
        default_factory=lambda: {"tone": "", "stress": "", "length": ""}
    )

    @property
    def text(self) -> str:
        return self.onset + self.nucleus + self.coda

    def match_constraint(self, constraint: dict) -> bool:
        if not constraint:
            return True
        onset_constraint = constraint.get("onset", "")
        nucleus_constraint = constraint.get("nucleus", "")
        coda_constraint = constraint.get("coda", "")
        attr_constraints = constraint.get("attributes", {})

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

    def to_dict(self) -> dict:
        return {
            "onset": self.onset,
            "nucleus": self.nucleus,
            "coda": self.coda,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Syllable":
        attrs = d.get("attributes", {})
        return cls(
            onset=d.get("onset", ""),
            nucleus=d.get("nucleus", ""),
            coda=d.get("coda", ""),
            attributes={
                "tone": attrs.get("tone", ""),
                "stress": attrs.get("stress", ""),
                "length": attrs.get("length", ""),
            },
        )
