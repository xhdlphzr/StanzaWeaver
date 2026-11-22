# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Unit tests for the Syllable data model (symbol layer)."""

from src.models.syllable import Syllable


def test_text_concatenates_parts() -> None:
    """Verify text concatenates the parts."""
    s = Syllable(onset="zh", nucleus="a", coda="ng")
    assert s.text == "zhang"


def test_match_constraint_empty_always_passes() -> None:
    """Verify an empty constraint always matches."""
    s = Syllable(onset="b", nucleus="a", coda="")
    assert s.match_constraint({}) is True


def test_match_constraint_onset_mismatch() -> None:
    """Verify match_constraint reports onset mismatches."""
    s = Syllable(onset="zh", nucleus="a", coda="")
    assert s.match_constraint({"onset": "z"}) is False
    assert s.match_constraint({"onset": "zh"}) is True


def test_match_constraint_nucleus_and_coda() -> None:
    """Verify match_constraint checks nucleus and coda."""
    s = Syllable(onset="", nucleus="iao", coda="ng")
    assert s.match_constraint({"nucleus": "iao", "coda": "ng"}) is True
    assert s.match_constraint({"nucleus": "ia"}) is False
    assert s.match_constraint({"coda": "n"}) is False


def test_match_constraint_attributes() -> None:
    """Verify match_constraint checks attributes."""
    s = Syllable(attributes={"tone": "平", "stress": "", "length": ""})
    assert s.match_constraint({"attributes": {"tone": "平"}}) is True
    assert s.match_constraint({"attributes": {"tone": "仄"}}) is False


def test_to_dict_from_dict_roundtrip() -> None:
    """Verify the to_dict/from_dict round trip."""
    s = Syllable(onset="x", nucleus="ü", coda="", attributes={"tone": "仄"})
    d = s.to_dict()
    # to_dict emits the stored attributes as-is (no default values filled in).
    assert d == {
        "onset": "x",
        "nucleus": "ü",
        "coda": "",
        "attributes": {"tone": "仄"},
    }
    # from_dict fills in missing default attributes.
    restored = Syllable.from_dict(d)
    assert restored.onset == "x"
    assert restored.nucleus == "ü"
    assert restored.attributes["tone"] == "仄"
    assert restored.attributes["stress"] == ""
    assert restored.attributes["length"] == ""
