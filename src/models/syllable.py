# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Data model: syllable.

The smallest unit of prosodic analysis: onset, nucleus, coda, and phonological
attributes such as tone/stress/length. Syllable analyzers for every language
produce this structure.
"""

from dataclasses import dataclass, field
from typing import Any

TONE_LABEL = str  # "" | "平" | "仄"
STRESS_LABEL = str  # "" | "heavy" | "light"
LENGTH_LABEL = str  # "" | "long" | "short"


@dataclass
class Syllable:
    """A single syllable.

    Attributes:
        onset: Initial consonant (e.g. "str" in English, "zh" in Chinese).
        nucleus: Vowel core (e.g. "a" or "iao" in Chinese, "IY" in English).
        coda: Final consonant (e.g. "ng" in Chinese, "T" in English).
        attributes: Phonological attribute dict keyed by tone/stress/length.

    """

    onset: str = ""
    nucleus: str = ""
    coda: str = ""
    attributes: dict[str, str] = field(
        default_factory=lambda: {"tone": "", "stress": "", "length": ""}
    )

    @property
    def text(self) -> str:
        """Return the full spelling of the syllable (onset + nucleus + coda).

        Returns:
            The spelling string.

        """
        return self.onset + self.nucleus + self.coda

    def match_constraint(self, constraint: dict[str, Any]) -> bool:
        """Check whether this syllable satisfies one positional constraint.

        The constraint dict may contain onset/nucleus/coda plus an ``attributes``
        sub-dict; an empty field means unconstrained. Only explicitly given
        fields are compared.

        Args:
            constraint: Constraint dict, e.g.
                ``{"onset": "zh", "attributes": {"tone": "平"}}``.

        Returns:
            True if all constraints are satisfied, otherwise False.

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
        """Serialize the syllable to a JSON-serializable dictionary.

        Returns:
            ``{"onset": ..., "nucleus": ..., "coda": ..., "attributes": {...}}``.

        """
        return {
            "onset": self.onset,
            "nucleus": self.nucleus,
            "coda": self.coda,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Syllable:
        """Rebuild a syllable from a dictionary (inverse of :meth:`to_dict`).

        Args:
            d: Dictionary produced by ``to_dict()``.

        Returns:
            The reconstructed Syllable instance.

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
