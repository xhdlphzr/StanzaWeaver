# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""通用押韵检查（供自定义模板的韵式配置使用）.

自定义模板允许用户按行配置韵式（如 ``ABAB CDCD EFEF GG``），本模块把
各语言的韵脚 key 统一归一，供生成的模板在 ``validate_full`` 中调用：

- 汉语：按《中华通韵》韵部归并（复用 templates.zh._rhyme_key）；
- 英语：严格重音押韵（复用 EnglishAnalyzer.rhyme_tails）；
- 法语：词末发音元音核（复用 FrenchAnalyzer.rhyme_key）；
- 意大利语 / 拉丁语：行末音节韵腹+韵尾；
- 其他语言：退回通用音节韵腹+韵尾。

同一韵组的行必须共享至少一个韵脚 key；“不同韵脚互异”开启时，任意两个
不同韵组不得共享 key。
"""

import re

from ..models.syllable import Syllable
from ..prosody.syllable_counter import get_analyzer

#: 韵式中表示“该行不押韵”的字符（统一归一为 "-"）。
_NO_RHYME_CHARS = frozenset({"-", ".", "X", "*", "_"})

#: 韵式中的分隔符（空白、逗号、斜杠、竖线等，便于书写 ABAB, CDCD）。
_SEPARATOR_RE = re.compile(r"[\s,;/|]+")

#: 提取行末单词（用于英语/法语等按词押韵的语言）。
_WORD_RE = re.compile(r"[^\W\d_]+(?:['\u2019\-][^\W\d_]+)*", re.UNICODE)


def _last_word(line: str) -> str:
    """取一行中的最后一个单词（保留词内撇号/连字符）.

    Args:
        line: 一行诗。

    Returns:
        行末单词（小写）；无单词时返回空串。

    """
    words = _WORD_RE.findall(line)
    return words[-1].lower() if words else ""


def _syllable_rhyme_key(syl: Syllable) -> str:
    """通用音节韵脚 key：韵腹 + 韵尾.

    Args:
        syl: 行末音节。

    Returns:
        韵脚 key；韵腹韵尾皆空时返回空串。

    """
    return f"{syl.nucleus or ''}{syl.coda or ''}"


def _last_syllable(
    language: str, line: str, syllables: list[Syllable] | None
) -> Syllable | None:
    """取一行的行末音节（优先使用已给出的切分变体）.

    Args:
        language: 语言代码。
        line: 一行诗。
        syllables: 该行已分析好的音节（可为 None）。

    Returns:
        行末音节；无法分析时返回 None。

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
    """返回一行可接受的韵脚 key 集合.

    多发音/多读音的行可能对应多个可行韵脚，只要韵组内任一行与其它行共享
    至少一个 key 即视为押韵。

    Args:
        language: 语言代码（zh/en/fr/it/la 等）。
        line: 一行诗。
        syllables: 该行已分析好的音节（可选，用于多音字变体）。

    Returns:
        韵脚 key 集合；该行无法作韵脚时返回 None。

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
    # 空 key 或 "?"（无法归韵）均视为不能作韵脚。
    if not key or key == "?":
        return None
    return {f"{language}:{key}"}


def parse_rhyme_scheme(scheme: str) -> list[str | None]:
    """把韵式字符串解析为逐行韵组（None 表示该行不押韵）.

    Args:
        scheme: 韵式字符串，如 ``ABAB CDCD EFEF GG`` 或 ``ABAB--``。

    Returns:
        逐行韵组字母列表（大写）；不押韵的行为 None。

    """
    cleaned = _normalize_scheme_text(scheme)
    return [None if ch == "-" else ch for ch in cleaned]


def _normalize_scheme_text(scheme: str) -> str:
    """归一化韵式文本：去分隔符、转大写、不押韵标记统一为 "-".

    Args:
        scheme: 原始韵式。

    Returns:
        归一化后的韵式字符串。

    """
    cleaned = _SEPARATOR_RE.sub("", str(scheme)).upper()
    return "".join("-" if ch in _NO_RHYME_CHARS else ch for ch in cleaned)


def normalize_rhyme_scheme(scheme: str, lines: int) -> tuple[str, str | None]:
    """校验并归一化韵式（供创建模板接口使用）.

    Args:
        scheme: 用户输入的韵式（可为空）。
        lines: 模板行数。

    Returns:
        (归一化韵式, 错误信息)；合法时错误信息为 None。

    """
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return "", None
    for ch in cleaned:
        if ch == "-":
            continue
        if not ("A" <= ch <= "Z"):
            return "", f"韵式含非法字符 {ch!r}，只能使用字母或 '-'"
    if len(cleaned) != lines:
        return "", f"韵式长度应为 {lines}，实际 {len(cleaned)}（可含空格分隔）"
    return cleaned, None


def _format_keys(keys: set[str]) -> str:
    """把韵脚 key 集合格式化为可读文本（去掉语言前缀）.

    Args:
        keys: 韵脚 key 集合。

    Returns:
        形如 ``AY1 T`` 的可读文本。

    """
    return "/".join(sorted(key.split(":", 1)[-1] for key in keys))


def check_rhyme_scheme(
    language: str,
    poem: list[str],
    scheme: str,
    distinct: bool = False,
    syllables: list[list[Syllable]] | None = None,
) -> list[str]:
    """按韵式检查押韵.

    Args:
        language: 语言代码。
        poem: 诗行列表（正文行）。
        scheme: 韵式（如 ``ABAB CDCD EFEF GG``）。
        distinct: 为 True 时要求不同韵组互不押韵。
        syllables: 各行音节（可选，用于多音字变体）。

    Returns:
        错误信息列表；全部满足时返回空列表。

    """
    errors: list[str] = []
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return errors
    if len(cleaned) > len(poem):
        errors.append(
            f"韵式共有 {len(cleaned)} 行，超过诗稿行数 {len(poem)}，无法检查押韵"
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
                    f"押韵{label}: 第{idx + 1}行无法确定韵脚（可能无重读音节或空行）"
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
                f"押韵{label}不匹配: 第{first_idx + 1}行韵脚为'{_format_keys(first_keys)}'，"
                f"第{last_idx + 1}行韵脚为'{_format_keys(last_keys)}'，不押韵"
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
                        f"不同韵组应互不相同: 韵组{labels[i]}与{labels[j]}共享韵脚"
                        f"'{_format_keys(shared)}'"
                    )
    return errors


def rhyme_scheme_description(scheme: str) -> str:
    """生成韵式的人类可读描述（写入模板 rule_description）.

    Args:
        scheme: 韵式字符串。

    Returns:
        描述文本；空韵式返回空串。

    """
    cleaned = _normalize_scheme_text(scheme)
    if not cleaned:
        return ""
    grouped = " ".join(cleaned[i : i + 4] for i in range(0, len(cleaned), 4))
    return f"韵式 {grouped}"
