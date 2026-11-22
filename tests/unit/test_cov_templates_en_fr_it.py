# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Coverage completion tests for the four src/templates modules.

Raises line coverage of __init__/en/fr/it to 100%. Only new test cases are
added: minimal stub templates, specific inputs, and a mocked English analyzer
exercise the branches that en/fr/it/__init__ still leave uncovered.
"""

from collections.abc import Generator
from typing import ClassVar

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.models.syllable import Syllable
from src.templates import (
    ConstraintTable,
    PoetryTemplate,
    _make_syl,
    format_count,
    list_all,
    list_dicts,
)
from src.templates import en as en_module
from src.templates import fr as fr_module
from src.templates.en import (
    HeroicCoupletTemplate,
    ShakespeareSonnetTemplate,
    VillanelleTemplate,
    _en_rhyme_key,
)
from src.templates.en import (
    _check_rhyme_group as en_check_rhyme_group,
)
from src.templates.en import (
    _check_stress_count as en_check_stress_count,
)
from src.templates.en import (
    _en_last_word as en_last_word,
)
from src.templates.fr import (
    BalladeTemplate,
    RondeauTemplate,
    TrioletTemplate,
)
from src.templates.fr import (
    _check_rhyme_group as fr_check_rhyme_group,
)
from src.templates.fr import (
    _fr_last_word as fr_last_word,
)
from src.templates.it import (
    CanzoneTemplate,
    OttavaRimaTemplate,
    TerzaRimaTemplate,
)


class _BareTemplate(PoetryTemplate):
    """Base-class stub overriding nothing (covers the base default branches)."""


class _ConstraintTemplate(PoetryTemplate):
    """Stub template with per-position constraints (onset/nucleus/coda)."""

    name = "测试约束模板"
    language = "xx"
    lines = 1
    syllables_per_line: ClassVar[list[int]] = [2]
    rule_description = "行覆盖用规则描述"

    def get_syllable_constraints(self) -> ConstraintTable:
        """Return a constraint table with onset/nucleus/coda and attributes."""
        return [
            [
                {
                    "onset": "b",
                    "nucleus": "a",
                    "coda": "t",
                    "attributes": {
                        "tone": "xx",
                        "stress": "heavy",
                        "length": "",
                    },
                }
            ]
        ]


@pytest.fixture()
def registry_snapshot() -> Generator[None]:
    """Restore the global _registry around the test so other cases are unaffected.

    Yields:
        Nothing (restoration runs after the yield).

    """
    from src.templates import _registry

    saved: dict[str, PoetryTemplate] = dict(_registry)
    yield
    _registry.clear()
    _registry.update(saved)


def test_base_get_syllable_constraints_returns_none() -> None:
    """Base get_syllable_constraints returns None (__init__ line 41)."""
    assert _BareTemplate().get_syllable_constraints() is None


def test_base_validate_full_returns_empty() -> None:
    """Base validate_full returns an empty list (__init__ line 55)."""
    assert _BareTemplate().validate_full([], []) == []


def test_describe_with_constraints_covers_branches() -> None:
    """Describe enters the per-position constraint branch (__init__ 83-98)."""
    desc = _ConstraintTemplate().describe()
    assert "onset=b" in desc
    assert "nucleus=a" in desc
    assert "coda=t" in desc
    assert "tone=xx" in desc


def test_format_count_tuple_branch() -> None:
    """format_count returns 'x-y' for a (min,max) range (__init__ 128)."""
    assert format_count((8, 10)) == "8-10"


def test_format_count_int_branch() -> None:
    """format_count returns the string form of an int (__init__ 129)."""
    assert format_count(5) == "5"


def test_list_all_returns_registered(registry_snapshot: None) -> None:
    """list_all returns every registered template (__init__ line 153)."""
    from src.templates import _registry

    _registry.clear()
    inst = _BareTemplate()
    _registry["cov_test"] = inst
    assert inst in list_all()


def test_list_dicts_label_and_fallback(registry_snapshot: None) -> None:
    """list_dicts covers both a known language label and the unknown fallback."""
    from src.templates import _registry

    _registry.clear()
    _registry["cov_en"] = ShakespeareSonnetTemplate()
    _registry["cov_xx"] = _ConstraintTemplate()
    dicts = list_dicts()
    names = [d["display_name"] for d in dicts]
    assert any("英语" in n for n in names)
    assert any("（xx）" in n for n in names)


def test_en_make_syl_non_dict_attributes() -> None:
    """_make_syl falls back to an empty dict for non-dict attributes (en 32)."""
    syl = _make_syl(attributes="not-a-dict")
    assert syl["attributes"] == {"tone": "", "stress": "", "length": ""}


def test_en_last_word_empty() -> None:
    """_last_word returns an empty string for a blank line (en 59)."""
    assert en_last_word("   ") == ""


def test_en_rhyme_key_empty_returns_none() -> None:
    """_en_rhyme_key returns None for a blank line (en 77)."""
    assert _en_rhyme_key("") is None


def test_en_check_stress_count_too_few() -> None:
    """_check_stress_count appends an error when stress is too sparse (en 98)."""
    errors: list[str] = []
    light = Syllable(attributes={"stress": "light"})
    en_check_stress_count(["a line"], [[light]], 4, errors)
    assert errors
    assert "too few stressed syllables" in errors[0]


def test_en_check_rhyme_group_out_of_range_index(
    monkeypatch: MonkeyPatch,
) -> None:
    """_check_rhyme_group skips out-of-range indices (en 115)."""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["AY1 T"])
    errors: list[str] = []
    en_check_rhyme_group(["word"], [0, 99], "A", errors)
    assert errors == []


def test_en_rhyme_key_no_tails_and_rhyme_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """_en_rhyme_key returns None without stressed tails (80) and adds an error.

    The error says the rhyme does not fall on a stress; covers en 118-119.
    """
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: [])
    assert _en_rhyme_key("word") is None
    errors: list[str] = []
    en_check_rhyme_group(["word"], [0], "A", errors)
    assert any("does not fall on a primary or secondary stressed" in e for e in errors)


def test_en_check_rhyme_group_mismatch(monkeypatch: MonkeyPatch) -> None:
    """A rhyme-tail mismatch within a group is reported (en 122-128)."""

    def _fake_tails(word: str) -> list[str]:
        """Mocked rhyme_tails: fixed tails per word to build a rhyme conflict.

        Args:
            word: Word whose rhyme tail is looked up.

        Returns:
            The rhyme-tail list.

        """
        return ["T1"] if word == "aaa" else ["T2"]

    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", _fake_tails)
    errors: list[str] = []
    en_check_rhyme_group(["aaa", "bbb"], [0, 1], "A", errors)
    assert any("Rhyme A mismatch" in e for e in errors)


def test_en_sonnet_ab_overlap(monkeypatch: MonkeyPatch) -> None:
    """The sonnet reports overlapping A/B rhymes in one quatrain (en 177, 183-186)."""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["X1"])
    monkeypatch.setattr(en_module, "_check_stress_count", lambda *a: None)
    poem = [f"line {i} x" for i in range(14)]
    errors = ShakespeareSonnetTemplate().validate_full(poem, [[]] * 14)
    assert any("A/B rhymes should differ" in e for e in errors)


def test_en_villanelle_ab_overlap(monkeypatch: MonkeyPatch) -> None:
    """The villanelle reports overlapping A/B rhymes (en 241)."""
    monkeypatch.setattr(en_module._EN_ANALYZER, "rhyme_tails", lambda word: ["AY1 T"])
    monkeypatch.setattr(en_module, "_check_stress_count", lambda *a: None)
    poem = ["the night", "the night"]
    heavy = Syllable(attributes={"stress": "heavy"})
    syllables: list[list[Syllable]] = [[heavy] * 5, [heavy] * 5]
    errors = VillanelleTemplate().validate_full(poem, syllables)
    assert any("A/B rhymes should differ" in e for e in errors)


def test_en_concrete_templates_methods() -> None:
    """Instantiate all English templates and call each public method."""
    for tmpl in (
        ShakespeareSonnetTemplate(),
        VillanelleTemplate(),
        HeroicCoupletTemplate(),
    ):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None or isinstance(
            tmpl.get_syllable_constraints(), list
        )
        assert isinstance(tmpl.validate_full([], []), list)


def test_fr_last_word_empty() -> None:
    """fr._last_word returns an empty string for a blank line (fr 30)."""
    assert fr_last_word("   ") == ""


def test_fr_check_rhyme_group_out_of_range_index(
    monkeypatch: MonkeyPatch,
) -> None:
    """fr._check_rhyme_group skips out-of-range indices (fr 48)."""
    monkeypatch.setattr(fr_module._FR, "rhyme_key", lambda w: "x")
    errors: list[str] = []
    fr_check_rhyme_group(["mot"], [0, 99], "A", errors)
    assert errors == []


def test_fr_ballade_invalid_syllable_count() -> None:
    """The ballade reports a first line whose count is not 8/10 (fr 170)."""
    syl = Syllable(nucleus="a", coda="t")
    syllables: list[list[Syllable]] = [[syl] * 5]
    errors = BalladeTemplate().validate_full([], syllables)
    assert any("Each ballade line should have 8 or 10 syllables" in e for e in errors)


def test_fr_concrete_templates_methods() -> None:
    """Instantiate all French templates and call each public method."""
    for tmpl in (RondeauTemplate(), TrioletTemplate(), BalladeTemplate()):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None
        assert isinstance(tmpl.validate_full([], []), list)


def test_it_canzone_too_many_rhymes() -> None:
    """The canzone reports more than 4 rhymes (it 203)."""
    syllables: list[list[Syllable]] = [
        [Syllable(nucleus=chr(ord("a") + i), coda="x")] for i in range(13)
    ]
    errors = CanzoneTemplate().validate_full(["x"] * 13, syllables)
    assert any("should use at most 4 rhymes" in e for e in errors)


def test_it_concrete_templates_methods() -> None:
    """Instantiate all Italian templates and call each public method."""
    for tmpl in (TerzaRimaTemplate(), OttavaRimaTemplate(), CanzoneTemplate()):
        assert tmpl.to_dict()["name"]
        assert tmpl.describe()
        assert tmpl.get_syllable_constraints() is None
        dummy: list[list[Syllable]] = [[Syllable()] for _ in range(tmpl.lines)]
        assert isinstance(tmpl.validate_full(["x"] * tmpl.lines, dummy), list)


def test_custom_template_schemes_all_five_languages() -> None:
    """custom_template_schemes covers zh/en/it/la/fr and their dimensions."""
    from src.templates import custom_template_schemes

    schemes = custom_template_schemes()
    assert set(schemes) == {"zh", "en", "fr", "it", "la"}
    assert schemes["zh"] == ("tone", ("平", "仄"))
    assert schemes["en"] == ("stress", ("light", "heavy"))
    assert schemes["it"] == ("stress", ("light", "heavy"))
    assert schemes["la"] == ("length", ("long", "short"))
    assert schemes["fr"] == ("", ())


def test_custom_template_schemes_returns_copy() -> None:
    """custom_template_schemes returns a copy; external edits do not leak in."""
    from src.templates import custom_template_schemes

    schemes = custom_template_schemes()
    schemes.pop("zh")
    schemes["xx"] = ("tone", ("平",))
    assert "zh" in custom_template_schemes()
    assert "xx" not in custom_template_schemes()


def test_template_helpers_lists_check_functions() -> None:
    """template_helpers returns the alphabetically sorted _check_* helpers."""
    from src.templates import template_helpers

    zh_helpers = template_helpers("zh")
    assert isinstance(zh_helpers, tuple)
    assert "_check_sanpingwei" in zh_helpers
    assert all(name.startswith("_check_") for name in zh_helpers)
    assert zh_helpers == tuple(sorted(zh_helpers))
    en_helpers = template_helpers("en")
    assert "_check_rhyme_group" in en_helpers
    fr_helpers = template_helpers("fr")
    assert "_check_rhyme_group" in fr_helpers
