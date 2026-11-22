# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""English syllable analyzer (based on CMUdict).

- CMUdict phoneme strings -> syllable division, assigning intervocalic
  consonants with standard English syllabification rules.
- Primary (1) and secondary (2) stress both count as stressed (secondary stress
  also occupies a stress position in poetic meter).
- Polyphonic words keep every pronunciation (read/present/record etc. differ by
  part of speech and meaning); validation passes if any pronunciation variant
  satisfies the meter.
- rhyme_tail builds a strict stress-rhyme key: the phoneme sequence from the
  last stressed vowel to the end of the word (including stress level), used for
  sonnet/couplet rhyme validation.
"""

import re
import threading

import nltk  # type: ignore[import-untyped]

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

_NUMBERS_RE = re.compile(r"\d+")

_VOWEL_PHONEMES = {
    "AA",
    "AE",
    "AH",
    "AO",
    "AW",
    "AX",
    "AXR",
    "AY",
    "EH",
    "ER",
    "EY",
    "IH",
    "IX",
    "IY",
    "OW",
    "OY",
    "UH",
    "UW",
    "UX",
}

# Primary (1) and secondary (2) stress are both stressed (secondary stress also
# occupies a stress position in poetic meter); unstressed (0) is marked
# "light" to match the _l constraint in templates, so that weak positions in
# iambic meter are forced to be unstressed.
_STRESS_MAP: dict[str, str] = {"0": "light", "1": "heavy", "2": "heavy"}

_ARPABET_TO_PHONEMES: dict[str, list[list[str]]] = {}
_cmudict_loaded = False
_cmudict_lock = threading.Lock()


def _load_cmudict() -> None:
    """Lazily load CMUdict into memory (thread-safe, loaded once).

    Keeps every pronunciation variant of each word.
    """
    global _cmudict_loaded
    if _cmudict_loaded:
        return
    with _cmudict_lock:
        if _cmudict_loaded:
            return
        try:
            nltk.data.find("corpora/cmudict.zip")
        except LookupError:
            nltk.download("cmudict", quiet=True)
        from nltk.corpus import cmudict  # type: ignore[import-untyped]

        for word, pronunciations in cmudict.dict().items():
            _ARPABET_TO_PHONEMES[str(word)] = pronunciations
        _cmudict_loaded = True


class EnglishAnalyzer(SyllableAnalyzer):
    """English syllable analyzer: division, stress, variants, and rhyme tails."""

    language = "en"

    def _get_pronunciations(self, word: str) -> list[list[str]]:
        """Look up all phoneme pronunciations of a word.

        Reads first from the local SQLite lexicon (the en_pron table), which
        also works offline; on a miss falls back to CMUdict (downloaded on
        first use and cached in memory).

        Args:
            word: English word.

        Returns:
            List of phoneme lists (each element is one pronunciation); an
            unknown word returns an empty list.

        """
        lowered = word.lower()
        from ..knowledge import vocabulary

        db_prons = vocabulary.get_en_pron(lowered)
        if db_prons is not None:
            return db_prons
        _load_cmudict()
        return _ARPABET_TO_PHONEMES.get(lowered, [])

    def rhyme_tail(self, word: str) -> str | None:
        """Return the rhyme tail from the last stressed vowel to the word end.

        The tail includes stress levels. Rhyming requires a strict stress
        match: the rhyme foot must fall on a primary/secondary stressed
        syllable, and all phonemes from that syllable onward (including stress
        digits) must match exactly.

        Args:
            word: English word.

        Returns:
            Rhyme tail string (e.g. "AY1 T"); None when there is no stressed
            syllable (cannot serve as a rhyme foot).

        """
        tails = self.rhyme_tails(word)
        return tails[0] if tails else None

    def rhyme_tails(self, word: str) -> list[str]:
        """Return every usable rhyme tail of the word across all pronunciations.

        Each pronunciation contributes the phoneme sequence from its last
        primary/secondary stressed syllable to the word end; multiple
        pronunciations of the same word are all returned (deduplicated), so
        rhyme validation passes when any pronunciation rhymes.

        Args:
            word: English word.

        Returns:
            List of rhyme tails (may contain several); empty when there is no
            stressed syllable.

        """
        prons = self._get_pronunciations(word)
        if not prons:
            return []
        result: list[str] = []
        seen: set[str] = set()
        for phones in prons:
            for i in range(len(phones) - 1, -1, -1):
                sm = _NUMBERS_RE.search(phones[i])
                if (
                    sm
                    and sm.group() in ("1", "2")
                    and _NUMBERS_RE.sub("", phones[i]) in _VOWEL_PHONEMES
                ):
                    tail = " ".join(phones[i:])
                    if tail not in seen:
                        seen.add(tail)
                        result.append(tail)
                    break
        return result

    def analyze_variants(self, word: str) -> list[list[Syllable]]:
        """Return the syllable division for every pronunciation of the word.

        Args:
            word: English word.

        Returns:
            One syllable list per pronunciation; unknown words fall back to a
            heuristic division.

        """
        prons = self._get_pronunciations(word)
        if not prons:
            return [self._fallback_analyze(word)]
        return [self._parse_phones(p) for p in prons]

    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze a word (the first pronunciation is the most common).

        Args:
            word: English word.

        Returns:
            List of syllables.

        """
        return self.analyze_variants(word)[0]

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Return candidate syllable divisions for a whole line (capped at 64).

        Combines the pronunciation variants of each word.

        Args:
            line: One line of verse (may contain multiple words).

        Returns:
            Candidate division list (at least one element).

        """
        words = [w for w in re.split(r"[^a-zA-Z0-9'-]+", line.lower()) if w]
        combos: list[list[Syllable]] = [[]]
        for w in words:
            variants = self.analyze_variants(w)
            new: list[list[Syllable]] = []
            for combo in combos:
                for v in variants:
                    new.append(combo + v)
                    if len(new) >= 64:
                        break
                if len(new) >= 64:
                    break
            combos = new[:64]
        return combos or [[]]

    def _parse_phones(self, phones: list[str]) -> list[Syllable]:
        """Convert a CMUdict phoneme string into a syllable division.

        Intervocalic consonant assignment rules (standard English
        syllabification):
        - Single consonant between two vowels: joins the preceding syllable
          when the preceding vowel is primary-stressed and the following one is
          not (hap-py, bet-ter, bi-ol-o-gy); otherwise it joins the following
          syllable (a-bout, re-spond).
        - Clusters of two or more consonants: the first consonant joins the
          preceding syllable and the rest join the following one (ex-tra,
          Mon-day).

        Args:
            phones: CMUdict phoneme list (with stress digits, e.g. ["B", "AE1",
                "T"]).

        Returns:
            List of syllables.

        """
        vpos = [
            i for i, p in enumerate(phones) if _NUMBERS_RE.sub("", p) in _VOWEL_PHONEMES
        ]
        if not vpos:
            return []

        n = len(phones)
        onset_runs: list[list[str]] = []
        for k, vi in enumerate(vpos):
            start = 0 if k == 0 else vpos[k - 1] + 1
            onset_runs.append([phones[j] for j in range(start, vi)])
        final_coda = [phones[j] for j in range(vpos[-1] + 1, n)]

        codas: list[list[str]] = [[] for _ in vpos]
        for k in range(len(vpos) - 1):
            run = onset_runs[k + 1]
            if not run:
                continue
            prev_stress = _NUMBERS_RE.search(phones[vpos[k]])
            curr_stress = _NUMBERS_RE.search(phones[vpos[k + 1]])
            prev_primary = prev_stress is not None and prev_stress.group() == "1"
            curr_primary = curr_stress is not None and curr_stress.group() == "1"
            if len(run) == 1 and prev_primary and not curr_primary:
                codas[k] = run
                onset_runs[k + 1] = []
            elif len(run) >= 2:
                codas[k] = run[:1]
                onset_runs[k + 1] = run[1:]
        codas[-1] = final_coda

        syllables: list[Syllable] = []
        for k, vi in enumerate(vpos):
            sm = _NUMBERS_RE.search(phones[vi])
            stress = _STRESS_MAP.get(sm.group() if sm else "", "")
            syllables.append(
                Syllable(
                    onset="".join(_NUMBERS_RE.sub("", p) for p in onset_runs[k]),
                    nucleus=_NUMBERS_RE.sub("", phones[vi]),
                    coda="".join(_NUMBERS_RE.sub("", p) for p in codas[k]),
                    attributes={"tone": "", "stress": stress, "length": ""},
                )
            )
        return syllables

    def _fallback_analyze(self, word: str) -> list[Syllable]:
        """Estimate syllables for an unknown word by counting vowel groups.

        Args:
            word: A word not in CMUdict.

        Returns:
            One placeholder syllable per vowel group (nucleus="?", no stress).

        """
        vowel_groups = re.findall(r"[aeiouy]+", word.lower())
        count = len(vowel_groups)
        if count == 0:
            count = 1
        return [
            Syllable(
                nucleus="?",
                attributes={"tone": "", "stress": "light", "length": ""},
            )
            for _ in range(count)
        ]
