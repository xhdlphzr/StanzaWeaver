# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Chinese syllable analyzer (based on pypinyin).

- FINAL_TO_PARTS final-splitting table: splits a pinyin final into nucleus plus
  coda.
- For whole-line analysis the caller joins the whole line and hands it to
  pypinyin once, so its lexicon can disambiguate polyphonic characters from
  context (弹琴 -> tán, 银行 -> háng).
- Tone mapping: tones 1/2 and the neutral tone (including no tone mark) map to
  平; tones 3/4 map to 仄.
"""

import warnings

# pypinyin<=0.55.0 triggers a codecs.open() deprecation warning on Python 3.14
# (the third-party library has not adapted yet); suppress that specific warning
# before import.
warnings.filterwarnings(
    "ignore",
    message=r"codecs\.open\(\) is deprecated.*",
    category=DeprecationWarning,
)

from pypinyin import Style, pinyin

from ..models.syllable import Syllable
from .base import SyllableAnalyzer

FINAL_TO_PARTS: dict[str, tuple[str, str]] = {
    "a": ("a", ""),
    "o": ("o", ""),
    "e": ("e", ""),
    "i": ("i", ""),
    "u": ("u", ""),
    "v": ("v", ""),
    "ü": ("ü", ""),
    "er": ("er", ""),
    "ai": ("ai", ""),
    "ei": ("ei", ""),
    "ao": ("ao", ""),
    "ou": ("ou", ""),
    "iu": ("iu", ""),
    "ui": ("ui", ""),
    "an": ("a", "n"),
    "en": ("e", "n"),
    "in": ("i", "n"),
    "un": ("u", "n"),
    "vn": ("v", "n"),
    "ün": ("ü", "n"),
    "ang": ("a", "ng"),
    "eng": ("e", "ng"),
    "ing": ("i", "ng"),
    "ong": ("o", "ng"),
    "ia": ("ia", ""),
    "ie": ("ie", ""),
    "ua": ("ua", ""),
    "uo": ("uo", ""),
    "ve": ("ve", ""),
    "üe": ("üe", ""),
    "iao": ("iao", ""),
    "uai": ("uai", ""),
    "ian": ("ia", "n"),
    "uan": ("ua", "n"),
    "van": ("va", "n"),
    "üan": ("üa", "n"),
    "iang": ("ia", "ng"),
    "uang": ("ua", "ng"),
    "iong": ("io", "ng"),
    "ueng": ("ue", "ng"),
}

CHINESE_INITIALS = frozenset(
    {
        "b",
        "p",
        "m",
        "f",
        "d",
        "t",
        "n",
        "l",
        "g",
        "k",
        "h",
        "j",
        "q",
        "x",
        "zh",
        "ch",
        "sh",
        "r",
        "z",
        "c",
        "s",
        "y",
        "w",
    }
)

_PING_TONES = {"1", "2"}
_ZE_TONES = {"3", "4"}


def _split_final(final_str: str) -> tuple[str, str]:
    """Split a toned final string into (nucleus, coda).

    Args:
        final_str: For example "iao3", "ang", or "üe4".

    Returns:
        (nucleus, coda); (final_str, "") unchanged when unrecognized.

    """
    if not final_str:
        return "", ""
    tone_char = final_str[-1]
    if tone_char.isdigit():
        base = final_str[:-1]
    else:
        base = final_str
        tone_char = ""
    base_lower = base.lower()
    nucleus, coda = FINAL_TO_PARTS.get(base_lower, (base, ""))
    return nucleus, coda


def _tone_to_pingze(tone_str: str) -> str:
    """Map a tone to a 平/仄 label.

    First tone, second tone and the neutral tone (including no tone mark) are
    all 平; third and fourth tone are 仄.

    Args:
        tone_str: Final string with a tone digit (e.g. "iao3"); a string
            without a tone mark (neutral/no tone) or an empty string is also
            treated as 平.

    Returns:
        "平" or "仄".

    """
    if not tone_str:
        return "平"
    if tone_str[-1].isdigit():
        t = tone_str[-1]
    else:
        # No tone mark means the neutral tone -> 平.
        return "平"
    if t in _PING_TONES:
        return "平"
    if t in _ZE_TONES:
        return "仄"
    # Unusual digits such as tone 5 (neutral) also map to 平.
    return "平"


class ChineseAnalyzer(SyllableAnalyzer):
    """Chinese syllable analyzer: per-character onset/nucleus/coda plus 平/仄.

    analyze_word accepts text of any length (including a whole line); pypinyin
    automatically picks the correct reading of polyphonic characters based on
    the phrase context.
    """

    language = "zh"

    def analyze_word(self, word: str) -> list[Syllable]:
        """Analyze Chinese text (one or more characters), first reading only.

        Kept as a single-reading interface for backward compatibility: returns
        the first variant of :meth:`analyze_word_variants`.

        Args:
            word: Chinese text, e.g. "弹琴" or a whole line of verse.

        Returns:
            One Syllable per character (tone label in attributes["tone"]).

        """
        variants = self.analyze_word_variants(word)
        if not variants:
            return []
        return variants[0]

    def analyze_word_variants(self, word: str) -> list[list[Syllable]]:
        """Return all polyphonic reading combinations of a word.

        Each character is passed to pypinyin in heteronym mode to obtain its
        candidate (onset, final) pairs, then the Cartesian product over all
        characters yields every reading of the whole word.

        At most 64 combinations are returned; excess combinations are truncated
        in generation order (deterministic truncation).

        Args:
            word: Chinese text, e.g. "中" or "弹琴".

        Returns:
            List of readings; each element is the Syllable sequence of one
            whole-word reading.

        """
        if not word:
            return []

        initials_list = pinyin(word, style=Style.INITIALS, strict=False, heteronym=True)
        finals_list = pinyin(
            word, style=Style.FINALS_TONE3, strict=False, heteronym=True
        )

        # Candidate Syllables per character: pair onsets with finals per reading
        # to avoid the onset x final Cartesian product creating non-existent
        # mixes (e.g. zh+ang2 for "长"). When several readings share the same
        # onset, pypinyin deduplicates INITIALS (e.g. "中" returns only
        # ['zh']), so align by broadcasting the length.
        candidates: list[list[Syllable]] = []
        for initials, finals in zip(initials_list, finals_list):
            if len(initials) == len(finals):
                pairs = list(zip(initials, finals))
            elif len(initials) == 1:
                pairs = [(initials[0], final) for final in finals]
            elif len(finals) == 1:
                pairs = [(onset, finals[0]) for onset in initials]
            else:
                pairs = list(zip(initials, finals))
            char_syls: list[Syllable] = []
            for onset_r, final_r in pairs:
                onset = str(onset_r) if onset_r else ""
                final_raw = str(final_r) if final_r else ""
                nucleus, coda = _split_final(final_raw)
                tone_label = _tone_to_pingze(final_raw)
                char_syls.append(
                    Syllable(
                        onset=onset,
                        nucleus=nucleus,
                        coda=coda,
                        attributes={
                            "tone": tone_label,
                            "stress": "",
                            "length": "",
                        },
                    )
                )
            # Deduplicate by content, preserving order.
            seen: set[tuple[str, str, str, str]] = set()
            deduped: list[Syllable] = []
            for syl in char_syls:
                key = (
                    syl.onset,
                    syl.nucleus,
                    syl.coda,
                    syl.attributes.get("tone", ""),
                )
                if key not in seen:
                    seen.add(key)
                    deduped.append(syl)
            candidates.append(deduped)

        # Per-character Cartesian product (capped at 64).
        result: list[list[Syllable]] = [[]]
        for char_syls in candidates:
            if not char_syls:
                char_syls = [
                    Syllable(
                        onset="",
                        nucleus="",
                        coda="",
                        attributes={"tone": "", "stress": "", "length": ""},
                    )
                ]
            new_result: list[list[Syllable]] = []
            for combo in result:
                for syl in char_syls:
                    new_result.append(combo + [syl])
            result = new_result
            if len(result) > 64:
                result = result[:64]
        return result

    def analyze_line_variants(self, line: str) -> list[list[Syllable]]:
        """Return all reading combinations of a whole line.

        First splits the line into Chinese characters via :meth:`tokenize_line`,
        calls :meth:`analyze_word_variants` per character to get candidate
        readings, then takes the Cartesian product over the whole line.

        At most 64 combinations are returned; excess combinations are truncated
        in generation order (deterministic truncation).

        Args:
            line: One line of verse.

        Returns:
            List of readings; each element is the Syllable sequence of one line
            reading.

        """
        chars = self.tokenize_line(line)
        if not chars:
            return []
        word_variants = [self.analyze_word_variants(ch) for ch in chars]

        result: list[list[Syllable]] = [[]]
        for wv in word_variants:
            if not wv:
                wv = [[]]
            new_result: list[list[Syllable]] = []
            for combo in result:
                for variant in wv:
                    new_result.append(combo + variant)
            result = new_result
            if len(result) > 64:
                result = result[:64]
        return result

    def tokenize_line(self, line: str) -> list[str]:
        """Split per character (keeping only Chinese characters).

        Args:
            line: One line of verse.

        Returns:
            List of Chinese characters.

        """
        return [
            ch
            for ch in line
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        ]
