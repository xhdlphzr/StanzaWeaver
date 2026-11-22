# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Latin syllable analyzer.

- Supports macrons (āēīōūȳ) and breve marks (ăĕĭŏŭ).
- Length determination: dictionary/symbol marks take precedence; without a
  mark, a diphthong (ae/oe/au/eu/ei/ui) is long, and a vowel followed by two or
  more consonants (including across words) is long; everything else is short.
- u after qu/gu/su followed by a vowel is consonantal (quō, lingua, suāvis) and
  does not form a syllable.
"""

import re
import unicodedata

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_LONG_MARKERS: dict[str, str] = {
    "ā": "a",
    "ē": "e",
    "ī": "i",
    "ō": "o",
    "ū": "u",
    "ȳ": "y",
    "Ā": "a",
    "Ē": "e",
    "Ī": "i",
    "Ō": "o",
    "Ū": "u",
    "Ȳ": "y",
}
_SHORT_MARKERS: dict[str, str] = {
    "ă": "a",
    "ĕ": "e",
    "ĭ": "i",
    "ŏ": "o",
    "ŭ": "u",
    "y̆": "y",
    "Ă": "a",
    "Ĕ": "e",
    "Ĭ": "i",
    "Ŏ": "o",
    "Ŭ": "u",
}
_VOWELS: set[str] = set("aeiouyāēīōūȳăĕĭŏŭAEIOUY")
_DIPHTHONGS: set[str] = {
    "ae",
    "oe",
    "au",
    "eu",
    "ei",
    "AE",
    "OE",
    "AU",
    "EU",
    "EI",
}
# Latin stops (muta): next to a liquid (l/r) they form muta cum liquida, which
# counts as only one consonant slot.
# Note: f is a fricative, not a stop, so "fl"/"fr" are not muta cum liquida.
_STOPS: set[str] = set("bcdgkpqt")

# Used only to test whether a word-final/word-initial letter is a vowel (after
# stripping combining marks).
_VOWEL_BASE: set[str] = set("aeiouy")


def _strip_macron(text: str) -> str:
    """Strip combining marks (macron/breve), keeping only ASCII lowercase.

    Used to normalize diphthongs with macrons such as "āe" to "ae" before a
    table lookup.

    Args:
        text: String that may contain combining marks.

    Returns:
        Pure ASCII lowercase form with combining marks removed.

    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


class LatinAnalyzer(SyllableAnalyzer):
    """Latin syllable analyzer: division + length (marks/diphthongs/consonants)."""

    language = "la"

    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze the syllables and vowel lengths of a word.

        Syllable = (onset consonants) + vowel nucleus (may be a diphthong) +
        (coda consonants).
        - Consonantal u (qu/gu/su followed by a vowel) forms the whole cluster
          as the onset of the current syllable and does not create a separate
          syllable.
        - muta cum liquida (stop + liquid clusters) attaches to the current
          syllable (counted in the onset) and is not split backwards; other
          following consonants become the coda of the current syllable (except
          the last consonant; length is determined by the effective coda slots).
        - Length: a macron/diphthong is long; an effective coda of >= 2
          consonant slots is also long (x counts as 2).

        Args:
            word: Latin word (may contain length marks).

        Returns:
            Syllable list (length in attributes["length"]).

        """
        word = word.strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        syllables: list[Syllable] = []
        onset = ""
        nucleus = ""
        coda = ""
        length_val = ""

        def _close() -> None:
            """Close the pending syllable and append it to the list.

            Resets the local onset/nucleus/coda/length afterwards.
            """
            syllables.append(
                Syllable(
                    onset=onset,
                    nucleus=nucleus,
                    coda=coda,
                    attributes={
                        "tone": "",
                        "stress": "",
                        "length": length_val or "short",
                    },
                )
            )

        i = 0
        n = len(word)
        trailing: list[str] = []
        while i < n:
            ch = word[i]
            lower = ch.lower()
            # Consonantal u: after qu / gu / su followed by a vowel, the cluster
            # goes to trailing as the next syllable's onset.
            if lower == "q" or (
                lower in "gs"
                and i + 1 < n
                and word[i + 1].lower() == "u"
                and i + 2 < n
                and word[i + 2] in _VOWELS
            ):
                if nucleus:
                    coda = "".join(trailing)
                    _close()
                    onset = ""
                    nucleus = ""
                    coda = ""
                    length_val = ""
                trailing.append(lower)
                trailing.append("u")
                i += 2
                continue
            if ch in _VOWELS:
                if nucleus:
                    _close()
                    onset = ""
                    nucleus = ""
                    coda = ""
                    length_val = ""
                vowel_base = ch
                is_long = False
                if ch in _LONG_MARKERS:
                    vowel_base = _LONG_MARKERS[ch]
                    is_long = True
                elif ch in _SHORT_MARKERS:
                    vowel_base = _SHORT_MARKERS[ch]
                cand_norm = (
                    _strip_macron(lower + word[i + 1].lower()) if i + 1 < n else ""
                )
                if i + 1 < n and cand_norm in _DIPHTHONGS:
                    nucleus = cand_norm
                    is_long = True
                    i += 1
                else:
                    nucleus = vowel_base.lower()

                # The accumulated leading consonants become the current onset.
                onset = "".join(trailing)
                trailing = []

                # Collect following consonants; stop at a vowel or consonantal u.
                j = i + 1
                cons: list[str] = []
                while (
                    j < n
                    and word[j] not in _VOWELS
                    and not (
                        word[j].lower() == "q"
                        or (
                            word[j].lower() in "gs"
                            and j + 1 < n
                            and word[j + 1].lower() == "u"
                            and j + 2 < n
                            and word[j + 2] in _VOWELS
                        )
                    )
                ):
                    if word[j] not in " .-":
                        cons.append(word[j].lower())
                    j += 1
                trailing = cons
                eff = 0
                for c in cons:
                    eff += 2 if c == "x" else 1
                if not is_long and eff >= 2:
                    is_long = True
                length_val = "long" if is_long else "short"
                i = j
            else:
                trailing.append(lower)
                i += 1

        if nucleus:
            coda = "".join(trailing)
            _close()

        return (
            syllables
            if syllables
            else [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]
        )

    def analyze_line(self, text: str) -> list[Syllable]:
        """Analyze a whole line (cross-word length and Latin elision included).

        Cross-word length: if the final vowel of a word is followed by >= 2
        consonants at the start of the next word, it is long.
        Elision: when the preceding word ends in a vowel (or m) and the next
        word starts with a vowel (or h), the preceding word's final syllable is
        swallowed, reducing the syllable count by one.

        Args:
            text: One line of Latin text.

        Returns:
            Syllable list.

        """
        words = [w for w in re.split(r"[^A-Za-zāēīōūȳăĕĭŏŭ'-]+", text) if w]
        result: list[Syllable] = []
        m = len(words)
        for wi, w in enumerate(words):
            syls = self.analyze_word(w)
            if not syls:
                continue
            elided = False
            if wi + 1 < m:
                last_char = w[-1].lower()
                if last_char in _VOWEL_BASE or last_char == "m":
                    nxt_word = words[wi + 1].lower()
                    nstart_char = next((c for c in nxt_word if c.isalpha()), "")
                    if nstart_char in _VOWEL_BASE or nxt_word.startswith("h"):
                        elided = True
            if elided:
                # Elision: the preceding word's final vowel (or m) is swallowed
                # by the next word's initial vowel/h, removing one syllable.
                syls = syls[:-1]
            elif wi + 1 < m:
                lead = self._leading_consonant_count(words[wi + 1])
                if lead >= 2:
                    syls[-1].attributes["length"] = "long"
            result.extend(syls)
        return result

    @staticmethod
    def _leading_consonant_count(w: str) -> int:
        """Count the effective consonant slots in a word-initial consonant run.

        x counts as 2, u in qu/gu/su is consonantal, and muta cum liquida counts
        as only 1.

        Args:
            w: Latin word.

        Returns:
            Number of effective consonant slots; 0 when there is no leading
            consonant.

        """
        w = w.strip(".,;:!?\"'()[]{}").lower()
        n = len(w)
        i = 0
        cons: list[str] = []
        while i < n and w[i] not in _VOWELS:
            ch = w[i]
            if ch in "qgs" and i + 1 < n and w[i + 1] == "u":
                cons.append(ch + "u")
                i += 2
                continue
            cons.append(ch)
            i += 1
        eff = 0
        for c in cons:
            eff += 2 if c == "x" else 1
        if len(cons) == 2 and cons[0][0] in _STOPS and cons[1][0] in "lr":
            eff = 1
        return eff

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Return whole-line division variants (standard division only).

        In standard Latin scansion muta cum liquida merges into one beat, so
        only the standard division is returned.

        Args:
            line: One line of Latin verse.

        Returns:
            Variant list containing only the standard division.

        """
        return [self.analyze_line(line)]
