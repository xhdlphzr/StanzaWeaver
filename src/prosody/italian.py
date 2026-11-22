# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Italian syllable analyzer.

- Orthographic syllable division (digraphs read together) plus heuristic word
  stress: a final stressed vowel (città, perché, virtù) or a consonant-final
  word (amor) -> last syllable stressed; otherwise -> penultimate syllable
  stressed (the most common stress position in Italian).
  Note: the few words stressed on the antepenultimate syllable (sdrucciole)
  cannot be determined from spelling; this is a known limitation.
- syllabify_line handles line-level sinalefe (the final vowel of a word and the
  initial vowel of the next are read as one syllable) and elision apostrophes
  (l'amor -> amor), used for hendecasyllable counting.
"""

import re

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_VOWELS: set[str] = set("aeiouàèéìòóùAEIOUÀÈÉÌÒÓÙ")
_DIPHTHONGS: set[str] = {
    "ia",
    "ie",
    "io",
    "iu",
    "ua",
    "ue",
    "uo",
    "ui",
    "ai",
    "ei",
    "oi",
    "au",
    "eu",
    "ou",
}
_ACCENTED_VOWELS: set[str] = set("àèéìòóù")
_APOSTROPHE_RE = re.compile(r"^[a-zA-ZàèéìòóùÀÈÉÌÒÓÙ]*['’]")
_WORD_SPLIT_RE = re.compile(r"[^a-zA-ZàèéìòóùÀÈÉÌÒÓÙ0-9'’\-]+")


class ItalianAnalyzer(SyllableAnalyzer):
    """Italian syllable analyzer: division, stress heuristic, line-level sinalefe."""

    language = "it"

    def count_syllables_in_word(self, word: str) -> int:
        """Return the syllable count of a word (digraphs merged, stress splits).

        When either character of a candidate i/u digraph carries an accent mark
        (à è é ì ò ó ù), the pair is not merged and counts as two syllables
        (hiatus).

        Args:
            word: Italian word.

        Returns:
            Syllable count (at least 1).

        """
        word = _APOSTROPHE_RE.sub("", word.lower().strip(".,;:!?\"'()[]{}"))
        if not word:
            return 0
        i = 0
        n = len(word)
        count = 0
        while i < n:
            if word[i] in _VOWELS:
                count += 1
                if (
                    i + 1 < n
                    and word[i : i + 2] in _DIPHTHONGS
                    and word[i] not in _ACCENTED_VOWELS
                    and word[i + 1] not in _ACCENTED_VOWELS
                ):
                    i += 1
            i += 1
        return count if count > 0 else 1

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """Divide a word into syllables and mark stress (heuristic).

        The i/u carrying a stressed vowel (e.g. ì) does not form a digraph with
        the following vowel; it splits into two syllables instead. The stress
        position is decided by :meth:`_mark_word_stress`.

        Args:
            word: Italian word.

        Returns:
            Syllable list (stress in attributes["stress"], "heavy" when
            stressed).

        """
        w = _APOSTROPHE_RE.sub("", word.lower())
        if not w:
            return []
        syls: list[Syllable] = []
        i = 0
        n = len(w)
        onset = ""
        while i < n:
            if w[i] in _VOWELS:
                if (
                    i + 1 < n
                    and w[i : i + 2] in _DIPHTHONGS
                    and w[i] not in _ACCENTED_VOWELS
                    and w[i + 1] not in _ACCENTED_VOWELS
                ):
                    nucleus = w[i : i + 2]
                    i += 2
                else:
                    nucleus = w[i]
                    i += 1
                coda = ""
                while i < n and w[i] not in _VOWELS:
                    coda += w[i]
                    i += 1
                syls.append(
                    Syllable(
                        onset=onset,
                        nucleus=nucleus,
                        coda=coda,
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                )
                onset = ""
            elif w[i] == "q" and i + 1 < n and w[i + 1] == "u":
                onset += "qu"
                i += 2
            else:
                onset += w[i]
                i += 1
        if not syls:
            return [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]

        self._mark_word_stress(w, syls)
        return syls

    def _mark_word_stress(self, word: str, syls: list[Syllable]) -> None:
        """Mark stress by heuristic (written to each syllable's attributes).

        Rules:
        - A syllable with an explicit accent (à è é ì ò ó ù) is stressed;
        - ending in a consonant -> last syllable stressed (tronca);
        - ending in two consonants -> penultimate syllable stressed;
        - a polysyllabic word ending in a vowel -> penultimate syllable stressed
          (piana);
        - a monosyllabic word without an accent mark (e.g. la, mi) is treated as
          an unstressed particle.

        Args:
            word: Lowercased pure-letter word with elision apostrophes removed.
            syls: Already divided syllable list (modified in place).

        """
        n = len(syls)
        accent_idx = -1
        for idx, s in enumerate(syls):
            if any(ch in _ACCENTED_VOWELS for ch in s.nucleus):
                accent_idx = idx
                break

        if accent_idx >= 0:
            stress_idx = accent_idx
        elif word[-1] not in _VOWELS:
            if len(word) >= 2 and word[-2] not in _VOWELS:
                stress_idx = n - 2
            else:
                stress_idx = n - 1
        elif n == 1:
            stress_idx = -1
        else:
            stress_idx = n - 2

        if 0 <= stress_idx < n:
            syls[stress_idx].attributes["stress"] = "heavy"

    def syllabify_line(self, text: str) -> list[Syllable]:
        """Divide a whole line word by word, then apply cross-word sinalefe.

        When two vowels meet at a word boundary but either one is stressed
        (hiatus, e.g. virtù eterna), sinalefe is not applied and the two remain
        separate syllables.

        Args:
            text: One line of Italian verse.

        Returns:
            Syllable list for the whole line (elision handled, sinalefe merged
            where applicable).

        """
        words = [w for w in _WORD_SPLIT_RE.split(text.lower()) if w]
        all_syls: list[Syllable] = []
        for wi, w in enumerate(words):
            syls = self._syllabify_word(w)
            if not syls:
                continue
            if wi > 0:
                prev_clean = _APOSTROPHE_RE.sub("", words[wi - 1])
                curr_clean = _APOSTROPHE_RE.sub("", w)
                prev_syl = all_syls[-1] if all_syls else None
                can_sinalefe = (
                    prev_clean
                    and curr_clean
                    and prev_clean[-1] in _VOWELS
                    and curr_clean[0] in _VOWELS
                    and prev_syl is not None
                    and prev_syl.coda == ""
                )
                if can_sinalefe:
                    assert prev_syl is not None
                    prev_heavy = prev_syl.attributes.get("stress") == "heavy"
                    next_heavy = syls[0].attributes.get("stress") == "heavy"
                    if prev_heavy or next_heavy:
                        # Hiatus: do not merge; keep both syllables.
                        pass
                    else:
                        all_syls.pop()
            all_syls.extend(syls)
        return all_syls

    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze the syllables and stress of a word.

        Args:
            word: Italian word.

        Returns:
            Syllable list.

        """
        return self._syllabify_word(word)

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Return whole-line division variants (standard division only).

        Sinalefe is mandatory in standard Italian recitation, so a single
        variant is returned.

        Args:
            line: One line of Italian verse.

        Returns:
            Variant list containing only the standard division (sinalefe
            applied).

        """
        return [self.syllabify_line(line)]
