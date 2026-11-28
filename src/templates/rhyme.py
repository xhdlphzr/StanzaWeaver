# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Generic rhyme checking (for custom-template rhyme scheme configuration).

Custom templates let users configure a rhyme scheme per line (e.g.
``ABAB CDCD EFEF GG``). This module normalizes rhyme keys across languages so
generated templates can call it from ``validate_full``:

- Chinese: merged by the rhyme groups of *Zhonghua Tongyun* (reuses
  ``templates.zh._rhyme_key``);
- English: strict stress rhyme (reuses ``EnglishAnalyzer.rhyme_tails``);
- French: final pronounced vowel nucleus (reuses ``FrenchAnalyzer.rhyme_key``);
- Italian/Latin: nucleus + coda of the line's last syllable;
- Other languages: fall back to the generic nucleus + coda.

Lines of the same rhyme group must share at least one rhyme key; when "distinct
rhyme groups" is enabled, no two different groups may share a key.
"""

import re

from ..models.syllable import Syllable
from ..prosody.syllable_counter import get_analyzer

#: Characters meaning "this line does not rhyme" in a scheme (normalized to "-").
_NO_RHYME_CHARS = frozenset({"-", ".", "X", "*", "_"})

#: Separators in a scheme (whitespace, comma, slash, pipe, ...), so schemes can
#: be written as ABAB, CDCD.
_SEPARATOR_RE = re.compile(r"[\s,;/|]+")

#: Extract the last word of a line (for word-rhyming languages such as
#: English/French).
_WORD_RE = re.compile(r"[^\W\d_]+(?:['\u2019\-][^\W\d_]+)*", re.UNICODE)


def _last_word(line: str) -> str:
    """Get the last word of a line (keeping inner apostrophes/hyphens).

    Args:
        line: One line of poetry.

    Returns:
        Last word of the line (lowercased); empty string when there is no word.

    """
    words = _WORD_RE.findall(line)
    return words[-1].lower() if words else ""


def _syllable_rhyme_key(syl: Syllable) -> str:
    """Generic syllable rhyme key: nucleus + coda.

    Args:
        syl: The line's last syllable.

    Returns:
        Rhyme key; empty string when both nucleus and coda are empty.

    """
    return f"{syl.nucleus or ''}{syl.coda or ''}"


def _last_syllable(
    language: str, line: str, syllables: list[Syllable] | None
) -> Syllable | None:
    """Get the line's last syllable (preferring the given analyzed variant).

    Args:
        language: Language code.
        line: One line of poetry.
        syllables: Already analyzed syllables of the line (may be None).

    Returns:
        Last syllable of the line; None when it cannot be analyzed.

    """
    if syllables:
        return syllables[-1]
    variants = get_analyzer(language).analyze_line_variants(line)
    if not variants or not variants[0]:
        return None
    return variants[0][-1]


def rhyme_keys(
    language: str,
    line: str,
    syllables: list[Syllable] | None = None,
) -> set[str] | None:
    """Return the set of acceptable rhyme keys for a line.

    Lines with multiple pronunciations/readings may yield several viable rhyme
    keys; as long as any line in the group shares at least one key with the
    others, the group is considered to rhyme.

    Args:
        language: Language code (zh/en/fr/it/la, ...).
        line: One line of poetry.
        syllables: Already analyzed syllables of the line (optional, for
            polyphonic character variants).

    Returns:
        Set of rhyme keys; None when the line cannot serve as a rhyme.

    """
    if language == "en":
        word = _last_word(line)
        if not word:
            return None
        from ..prosody.english import EnglishAnalyzer

        tails = EnglishAnalyzer().rhyme_tails(word)
        return {f"en:{tail}" for tail in tails} if tails else None

    if language == "fr":
        word = _last_word(line)
        if not word:
            return None
        from ..prosody.french import FrenchAnalyzer

        key = FrenchAnalyzer().rhyme_key(word)
        return {f"fr:{key}"} if key else None

    last = _last_syllable(language, line, syllables)
    if last is None:
        return None
    if language == "zh":
        from .zh import _rhyme_key

        key = _rhyme_key(last)
    else:
        key = _syllable_rhyme_key(last)
    # An empty key or "?" (cannot be assigned to a rhyme group) means the line
    # cannot serve as a rhyme.
    if not key or key == "?":
        return None
    return {f"{language}:{key}"}


def parse_rhyme_scheme(scheme: str) -> list[str | None]:
    """Parse a rhyme-scheme string into per-line rhyme groups (None = no rhyme).

    Args:
        scheme: Rhyme-scheme string, e.g. ``ABAB CDCD EFEF GG`` or ``ABAB--``.

    Returns:
        List of per-line rhyme-group letters (uppercase); non-rhyming lines are
        None.

    """
    cleaned = _normalize_scheme_text(scheme)
    return [None if ch == "-" else ch for ch in cleaned]


def _normalize_scheme_text(scheme: str) -> str:
    """Normalize rhyme-scheme text: drop separators, uppercase, unify no-rhyme marks to "-".

    Args:
        scheme: Raw rhyme scheme.

    Returns:
        Normalized rhyme-scheme string.

    """
    cleaned = _SEPARATOR_RE.sub("", str(scheme)).upper()
    return "".join("-" if ch in _NO_RHYME_CHARS else ch for ch in cleaned)


def normalize_rhyme_scheme(scheme: str, lines: int) -> tuple[str, str | None]:
    """Validate and normalize a rhyme scheme (for the template-creation API).

    Args:
        scheme: User-entered rhyme scheme (may be empty).
        lines: Template line count.

    Returns:
        (Normalized rhyme scheme, error message); error is None when valid.

    """
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return "", None
    for ch in cleaned:
        if ch == "-":
            continue
        if not ("A" <= ch <= "Z"):
            return "", f"Rhyme scheme has invalid character {ch!r}; use letters or '-'"
    if len(cleaned) != lines:
        return "", (
            f"Rhyme scheme length should be {lines} but is {len(cleaned)} "
            f"(spaces may be used as separators)"
        )
    return cleaned, None


def _format_keys(keys: set[str]) -> str:
    """Format a set of rhyme keys as readable text (without language prefixes).

    Args:
        keys: Set of rhyme keys.

    Returns:
        Readable text such as ``AY1 T``.

    """
    return "/".join(sorted(key.split(":", 1)[-1] for key in keys))


def check_rhyme_scheme(
    language: str,
    poem: list[str],
    scheme: str,
    distinct: bool = False,
    syllables: list[list[Syllable]] | None = None,
) -> list[str]:
    """Check rhyme against a rhyme scheme.

    Args:
        language: Language code.
        poem: List of poem lines (body lines).
        scheme: Rhyme scheme (e.g. ``ABAB CDCD EFEF GG``).
        distinct: When True, different rhyme groups must not rhyme with each
            other.
        syllables: Syllables per line (optional, for polyphonic variants).

    Returns:
        List of error messages; empty when everything passes.

    """
    errors: list[str] = []
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return errors
    if len(cleaned) > len(poem):
        errors.append(
            f"Rhyme scheme has {len(cleaned)} lines, more than the poem's "
            f"{len(poem)} lines; cannot check rhyme"
        )
        return errors

    groups: dict[str, list[int]] = {}
    for idx, ch in enumerate(cleaned):
        if ch == "-":
            continue
        groups.setdefault(ch, []).append(idx)

    group_keys: dict[str, set[str]] = {}
    for label, indices in groups.items():
        line_keys: list[tuple[int, set[str]]] = []
        for idx in indices:
            line_syls = syllables[idx] if syllables and idx < len(syllables) else None
            keys = rhyme_keys(language, poem[idx], line_syls)
            if keys is None:
                errors.append(
                    f"Rhyme {label}: cannot determine the rhyme of line "
                    f"{idx + 1} (no stressed syllable, or empty line)"
                )
                continue
            line_keys.append((idx, keys))
        if len(line_keys) < 2:
            continue
        common: set[str] = set(line_keys[0][1])
        for _, keys in line_keys[1:]:
            common &= keys
        if not common:
            first_idx, first_keys = line_keys[0]
            last_idx, last_keys = line_keys[-1]
            errors.append(
                f"Rhyme {label} mismatch: line {first_idx + 1} rhymes with "
                f"'{_format_keys(first_keys)}', but line {last_idx + 1} rhymes "
                f"with '{_format_keys(last_keys)}'; they do not rhyme"
            )
        union: set[str] = set()
        for _, keys in line_keys:
            union |= keys
        group_keys[label] = union

    if distinct:
        labels = sorted(group_keys)
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                shared = group_keys[labels[i]] & group_keys[labels[j]]
                if shared:
                    errors.append(
                        f"Different rhyme groups should be distinct: groups "
                        f"{labels[i]} and {labels[j]} share the rhyme "
                        f"'{_format_keys(shared)}'"
                    )
    return errors


def rhyme_scheme_description(scheme: str) -> str:
    """Generate a human-readable description of a rhyme scheme (for rule_description).

    Args:
        scheme: Rhyme-scheme string.

    Returns:
        Description text; empty string for an empty scheme.

    """
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return ""
    grouped = " ".join(cleaned[i : i + 4] for i in range(0, len(cleaned), 4))
    return f"Rhyme scheme {grouped}"
