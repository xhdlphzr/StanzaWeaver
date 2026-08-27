"""拉丁语音节分析器。

- 支持长音符号（āēīōūȳ）与短音符号（ăĕĭŏŭ）标注。
- 音长判定：词典/符号标注优先；无标注时双元音（ae/oe/au/eu/ei/ui）为长音，
  元音后跟两个及以上辅音（含跨词）为长音，其余为短音。
- qu/gu/su 后接元音时 u 为辅音性（quō、lingua、suāvis），不构成音节。
"""

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
    "ui",
    "AE",
    "OE",
    "AU",
    "EU",
    "EI",
    "UI",
}


class LatinAnalyzer(SyllableAnalyzer):
    """拉丁语音节分析器：音节切分 + 音长判定（符号/双元音/辅音位置）。"""

    language = "la"

    def analyze_word(self, word: str) -> list[Syllable]:
        """分析单词的音节与音长。

        Args:
            word: 拉丁语单词（可含长短音符号）。

        Returns:
            音节列表（长度标在 attributes["length"]）。
        """
        word = word.strip(".,;:!?\"'()[]{}")
        if not word:
            return []
        syllables: list[Syllable] = []
        i = 0
        n = len(word)
        onset = ""
        nucleus = ""
        length_val = ""

        while i < n:
            ch = word[i]
            # 辅音性 u: qu / gu / su 后接元音时 u 不构成音节（quō, lingua, suāvis）
            if ch.lower() == "q" or (
                ch.lower() in "gs"
                and i + 1 < n
                and word[i + 1].lower() == "u"
                and i + 2 < n
                and word[i + 2] in _VOWELS
            ):
                onset += ch.lower()
                if i + 1 < n and word[i + 1].lower() == "u":
                    onset += "u"
                    i += 1
                i += 1
                continue
            if ch in _VOWELS:
                if nucleus:
                    syllables.append(
                        Syllable(
                            onset=onset,
                            nucleus=nucleus,
                            attributes={"tone": "", "stress": "", "length": length_val},
                        )
                    )
                    onset = ""
                    length_val = ""
                vowel_base = ch
                is_long = False
                if ch in _LONG_MARKERS:
                    vowel_base = _LONG_MARKERS[ch]
                    is_long = True
                elif ch in _SHORT_MARKERS:
                    vowel_base = _SHORT_MARKERS[ch]

                if i + 1 < n and ch.lower() + word[i + 1].lower() in _DIPHTHONGS:
                    nucleus = ch.lower() + word[i + 1].lower()
                    is_long = True
                    i += 1
                else:
                    nucleus = vowel_base.lower()

                j = i + 1
                cons_count = 0
                while j < n and word[j] not in _VOWELS:
                    if word[j] not in " .-":
                        cons_count += 1
                    j += 1
                if not is_long and cons_count >= 2:
                    is_long = True
                length_val = "long" if is_long else "short"
            else:
                onset += ch.lower()
            i += 1

        if nucleus:
            syllables.append(
                Syllable(
                    onset=onset,
                    nucleus=nucleus or "?",
                    attributes={
                        "tone": "",
                        "stress": "",
                        "length": length_val or "short",
                    },
                )
            )
        elif onset:
            syllables.append(
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            )

        return (
            syllables
            if syllables
            else [
                Syllable(
                    nucleus="?", attributes={"tone": "", "stress": "", "length": ""}
                )
            ]
        )

    def count_syllables(self, text: str) -> int:
        """逐词统计音节总数。

        Args:
            text: 拉丁语文本。

        Returns:
            音节总数。
        """
        return sum(len(self.analyze_word(w)) for w in text.split() if w.strip())
