# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""French syllable analyzer.

- Orthographic syllable division: digraphs/trigraphs (ou/eau/ain etc.), nasal
  vowels, silent e.
- Apostrophes are removed as separators only; word-initial letter prefixes are
  not stripped, so words with embedded apostrophes such as aujourd'hui /
  quelqu'un / presqu'île are still divided using their full form.
- u after qu is always silent; u after gu followed by e/i/y is silent
  (quel/guerre do not count the u as a syllable).
- Final silent e rule: a word-final e muet (followed only by the silent
  consonants s/t/x/p or nothing) is dropped when the word has other vowel
  nuclei; it is kept when it is the only vowel (e.g. le/de/que).
- Across words only liaison is handled: a final consonant joins the next word's
  initial onset without changing the syllable count; cross-word vowel contact
  does not elide (French elision appears only inside a word form via the
  apostrophe, e.g. l'eau).
- The rhyme key is the final pronounced vowel nucleus (nasals merged), with
  word-final silent consonants discarded.
"""

import re

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_VOWELS: set[str] = set("aeiouyàâäéèêëîïôöùûüæœÿ")
# Vowels with a diaeresis do not take part in digraph merging (e.g. ï in naïf).
_TREMA: set[str] = {"ï", "ÿ", "ü"}

_FR_DIGRAPHS: set[str] = {
    # Trigraphs / three-letter nuclei
    "eau",
    "yeu",
    "yen",
    "oui",
    "eui",
    "ien",
    "oin",
    "ain",
    "ein",
    # Digraphs / nasal vowels
    "ou",
    "au",
    "an",
    "en",
    "on",
    "in",
    "un",
    "ai",
    "ei",
    "eu",
    "oi",
    "ui",
    "ia",
    "ie",
    "io",
    "iu",
    "ua",
    "ue",
    "uo",
    # Items retained from the original implementation
    "ay",
    "ey",
    "œu",
    "œ",
    "am",
    "em",
    "im",
    "om",
    "um",
}

# Word-final silent consonants (ignored in French rhyme, e.g. s/t/x/p).
_MUTE_FINALS: set[str] = set("stxp")

# Nasal vowel merging: front nasals -> "an", back nasals -> "on".
_NASAL_FRONT: set[str] = {
    "an",
    "en",
    "in",
    "un",
    "ain",
    "ein",
    "ien",
    "oin",
    "am",
    "em",
    "im",
    "um",
}
_NASAL_BACK: set[str] = {"on", "om"}

# Apostrophes (l', qu'il, aujourd'hui, quelqu'un, etc.) are always removed:
# elision apostrophes do not form syllables, and the remaining adjacent letters
# can be parsed directly (u after qu is excluded by the silent-u rule). Do not
# strip the word-initial letter prefix, or the real syllables of
# aujourd'hui/quelqu'un/presqu'île would be lost.
_PUNCT_RE = re.compile(r"[^a-zàâäéèêëîïôöùûüæœÿ]")

# Silent-u condition after gu: u forms no syllable when followed by e/i/y
# (guerre, guide, langue); u is pronounced normally when followed by a/o/u or
# at the word end (aigu, Guadeloupe). u after qu is always silent.
_SILENT_GU_FOLLOW: set[str] = set("eéèêëiîïy")


def _is_vowel(ch: str) -> bool:
    """Return whether a character is a French vowel (with accents and œ/æ/y).

    Args:
        ch: Single character.

    Returns:
        True if it is a vowel.

    """
    return ch in _VOWELS


class FrenchAnalyzer(SyllableAnalyzer):
    """French syllable analyzer: real syllable structure (nucleus/coda) + rhyme key."""

    language = "fr"

    def _is_silent_u(self, w: str, i: int) -> bool:
        """Return whether the 'u' at position i is silent (forms no syllable).

        u after qu is always silent; u after gu followed by e/i/y is silent.
        Otherwise (u after gu followed by a/o/u, a standalone vowel,
        word-initial, etc.) u is pronounced normally or forms part of a digraph.

        Args:
            w: Cleaned word.
            i: Index of the 'u'.

        Returns:
            True if silent.

        """
        if w[i] != "u" or i == 0:
            return False
        prev = w[i - 1]
        if prev == "q":
            return True
        return prev == "g" and i + 1 < len(w) and w[i + 1] in _SILENT_GU_FOLLOW

    def _clean_word(self, word: str) -> str:
        """Strip punctuation and lowercase the word.

        Elision apostrophes are removed too (l'amour -> lamour), but the
        word-initial letter prefix is not stripped so that words with embedded
        apostrophes such as aujourd'hui / quelqu'un / presqu'île keep their
        division.

        Args:
            word: French word (may contain elision apostrophes and punctuation).

        Returns:
            Cleaned lowercase word; an empty string means no actual content.

        """
        w = word.lower().strip()
        w = _PUNCT_RE.sub("", w)
        return w

    def _build_syllables(
        self, w: str, nuclei: list[tuple[int, int, str]]
    ) -> list[Syllable]:
        """Assemble syllables from the vowel-nucleus positions.

        Consonants before a nucleus become its onset; consonants after a nucleus
        become its coda.

        Args:
            w: Cleaned word.
            nuclei: Vowel nucleus list of (start, end, nucleus text) tuples.

        Returns:
            List of syllables.

        """
        attrs: dict[str, str] = {"tone": "", "stress": "", "length": ""}
        syls: list[Syllable] = []
        prev_end = 0
        for idx, (start, end, nuc) in enumerate(nuclei):
            next_start = nuclei[idx + 1][0] if idx + 1 < len(nuclei) else len(w)
            onset = w[prev_end:start]
            coda = w[end:next_start]
            syls.append(
                Syllable(onset=onset, nucleus=nuc, coda=coda, attributes=dict(attrs))
            )
            prev_end = end
        return syls

    def _apply_final_e(
        self, syls: list[Syllable], w: str, nuclei: list[tuple[int, int, str]]
    ) -> list[Syllable]:
        """Drop a word-final silent e (e muet).

        Drop condition: the last vowel nucleus is exactly the single letter "e"
        and the text after e (the word end) contains only silent consonants
        (s/t/x/p) or is empty; it is dropped as long as the word has another
        vowel nucleus. It is kept when it is the only vowel (e.g. le/de/que).

        Args:
            syls: Initially divided syllables.
            w: Cleaned word.
            nuclei: Vowel nucleus list.

        Returns:
            Processed syllable list.

        """
        if not syls:
            return syls
        last = syls[-1]
        if last.nucleus != "e":
            return syls
        after = w[nuclei[-1][1] :]
        if after and not all(c in _MUTE_FINALS for c in after):
            return syls
        if len(syls) == 1:
            return syls
        return syls[:-1]

    def _syllabify_word(self, word: str) -> list[Syllable]:
        """Divide a word into syllables (digraphs and final silent e handled).

        Args:
            word: French word (may contain elision prefixes and punctuation).

        Returns:
            Syllable list (nucleus is the real vowel nucleus, coda the trailing
            consonants).

        """
        w = self._clean_word(word)
        if not w:
            return [
                Syllable(
                    nucleus="?",
                    attributes={"tone": "", "stress": "", "length": ""},
                )
            ]

        nuclei: list[tuple[int, int, str]] = []
        i = 0
        n = len(w)
        while i < n:
            if _is_vowel(w[i]) and not self._is_silent_u(w, i):
                matched: str | None = None
                for length in (3, 2):
                    if i + length <= n and w[i : i + length] in _FR_DIGRAPHS:
                        matched = w[i : i + length]
                        i += length
                        break
                if matched is None:
                    matched = w[i]
                    i += 1
                nuclei.append((i - len(matched), i, matched))
            else:
                i += 1

        syls = self._build_syllables(w, nuclei)
        return self._apply_final_e(syls, w, nuclei)

    def _normalize_nucleus(self, nuc: str) -> str:
        """Merge a vowel nucleus into a rhyme equivalence class (nasal merging).

        Args:
            nuc: Raw vowel nucleus (possibly a digraph/trigraph or nasal vowel).

        Returns:
            Merged rhyme nucleus (front nasals -> "an", back nasals -> "on").

        """
        if nuc in _NASAL_FRONT:
            return "an"
        if nuc in _NASAL_BACK:
            return "on"
        return nuc

    def rhyme_key(self, word: str) -> str:
        """Return the French rhyme key: final pronounced vowel nucleus.

        Nasals are merged and word-final silent consonants are already
        discarded.

        Args:
            word: Word at the end of a line.

        Returns:
            Rhyme string (e.g. parle -> "e", an/en -> "an"); empty when the
            word cannot be divided.

        """
        syls = self._syllabify_word(word)
        if not syls:
            return ""
        last = syls[-1]
        if last.nucleus == "?":
            return ""
        return self._normalize_nucleus(last.nucleus)

    def count_syllables_in_word(self, word: str) -> int:
        """Return the syllable count of a word.

        Handles digraph/trigraph merging and the final silent e rule.

        Args:
            word: French word.

        Returns:
            Syllable count.

        """
        return len(self._syllabify_word(word))

    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze the syllables of a word.

        Args:
            word: French word.

        Returns:
            Syllable list.

        """
        return self._syllabify_word(word)

    def syllabify_line(self, text: str) -> list[Syllable]:
        """Divide a whole line word by word and apply cross-word liaison.

        When the preceding word ends in a consonant and the next word starts
        with a vowel, that consonant joins the next word's first syllable as a
        liaison onset (without changing the syllable count). Cross-word vowel
        contact does not elide (French elision appears only inside a word form
        via the apostrophe, e.g. l'eau).

        Args:
            text: One line of French verse.

        Returns:
            Syllable list for the whole line.

        """
        words = text.split()
        all_syls: list[Syllable] = []
        for w in words:
            syls = self._syllabify_word(w)
            if not syls:
                continue
            if all_syls and syls:
                prev = all_syls[-1]
                curr = syls[0]
                if prev.coda != "" and curr.onset == "":
                    # Liaison: final consonant moves to the next word as onset.
                    curr.onset = prev.coda
                    prev.coda = ""
            all_syls.extend(syls)
        return all_syls

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Return whole-line division variants (only one in standard French).

        Standard French syllabification yields a single division.

        Args:
            line: One line of French verse.

        Returns:
            Variant list containing only the standard division.

        """
        return [self.syllabify_line(line)]
