# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
from typing import Dict, Optional

from .base import SyllableAnalyzer
from ..models.syllable import Syllable

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

_STRESS_MAP = {"0": "", "1": "heavy", "2": "light"}

_ARPABET_TO_PHONEME: Dict[str, Dict[str, str]] = {}
_cmudict_loaded = False


def _load_cmudict():
    global _cmudict_loaded
    if _cmudict_loaded:
        return
    try:
        import nltk

        nltk.data.find("corpora/cmudict.zip")
    except LookupError:
        nltk.download("cmudict", quiet=True)
    from nltk.corpus import cmudict

    for word, pronunciations in cmudict.dict().items():
        _ARPABET_TO_PHONEME[word] = pronunciations[0]
    _cmudict_loaded = True


class EnglishAnalyzer(SyllableAnalyzer):
    language = "en"

    def analyze_word(self, word: str) -> list[Syllable]:
        _load_cmudict()
        key = word.lower()
        phones = _ARPABET_TO_PHONEME.get(key)

        if phones is None:
            return self._fallback_analyze(word)

        return self._parse_phones(phones)

    def _parse_phones(self, phones: list[str]) -> list[Syllable]:
        syllables = []
        current_onset: list[str] = []
        in_nucleus = False
        current_nucleus: Optional[str] = None
        current_stress = ""
        current_coda: list[str] = []

        for phone in phones:
            clean = _NUMBERS_RE.sub("", phone)
            stress_match = _NUMBERS_RE.search(phone)
            stress = stress_match.group() if stress_match else ""

            if clean in _VOWEL_PHONEMES:
                if current_nucleus is not None:
                    syllables.append(
                        Syllable(
                            onset="".join(current_onset),
                            nucleus=current_nucleus,
                            coda="".join(current_coda),
                            attributes={
                                "tone": "",
                                "stress": current_stress,
                                "length": "",
                            },
                        )
                    )
                    current_onset = []
                    current_coda = []
                current_nucleus = clean
                current_stress = _STRESS_MAP.get(stress, "")
                in_nucleus = True
            else:
                if in_nucleus and current_nucleus is not None:
                    current_coda.append(clean)
                else:
                    current_onset.append(clean)

        if current_nucleus is not None:
            syllables.append(
                Syllable(
                    onset="".join(current_onset),
                    nucleus=current_nucleus,
                    coda="".join(current_coda),
                    attributes={"tone": "", "stress": current_stress, "length": ""},
                )
            )

        return syllables

    def _fallback_analyze(self, word: str) -> list[Syllable]:
        vowel_groups = re.findall(r"[aeiouy]+", word.lower())
        count = len(vowel_groups)
        if count == 0:
            count = 1
        return [
            Syllable(
                nucleus="?",
                attributes={"tone": "", "stress": "", "length": ""},
            )
            for _ in range(count)
        ]

    def count_syllables(self, text: str) -> int:
        total = 0
        for word in text.split():
            total += len(self.analyze_word(word))
        return total
