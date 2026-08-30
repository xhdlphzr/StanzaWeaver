# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Coverage tests for the vocabulary importer module (src.knowledge.importer).

All cases use heavy mocking and never trigger a real network, file read, or
SQLite write:
- ``urllib.request.urlopen`` is mocked to feed in-memory dictionary snippets.
- Vocabulary-layer writers (insert_words / set_en_pron / _set_dataset) are
  patched to capture calls.
- Analyzer classes (FrenchAnalyzer / ItalianAnalyzer / LatinAnalyzer) are
  patched to return controlled syllable results.
- sys.modules is patched with nltk / cmudict stubs so English import never
  touches the network.
"""

import bz2
import gzip
import types
from typing import Any
from unittest import mock

from src.knowledge import importer as imp
from src.models.syllable import Syllable


def _mk_syl(nucleus: str = "?") -> Syllable:
    """Build a placeholder syllable (no tone/stress/length).

    Args:
        nucleus: Nucleus text.

    Returns:
        Placeholder Syllable instance.
    """
    return Syllable(
        nucleus=nucleus,
        attributes={"tone": "", "stress": "", "length": ""},
    )


def _urlopen_returning(data: bytes) -> mock.MagicMock:
    """Build a urlopen stub returning the given bytes (context-manager aware).

    Args:
        data: Bytes the stub should return (compressed or plain).

    Returns:
        A MagicMock usable as a ``urllib.request.urlopen`` replacement.
    """
    resp = mock.MagicMock()
    resp.read.return_value = data
    cm = mock.MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    opener = mock.MagicMock()
    opener.return_value = cm
    return opener


def _alpha(n: int) -> str:
    """Convert a positive integer into a purely alphabetic string.

    Produces a, b, ..., z, aa, ... so generated keys stay ``str.isalpha()``.

    Args:
        n: Positive integer.

    Returns:
        Alphabetic-only string.
    """
    s = ""
    while n > 0:
        s = chr(ord("a") + (n - 1) % 26) + s
        n = (n - 1) // 26
    return s


# ── _download_text ──


def test_download_text_success() -> None:
    """_download_text returns decoded text on success."""
    text = "hello lexique"
    with mock.patch("urllib.request.urlopen", _urlopen_returning(text.encode("utf-8"))):
        assert imp._download_text("http://example.com/x") == text


def test_download_text_oserror() -> None:
    """_download_text returns None on network failure."""
    with mock.patch("urllib.request.urlopen", side_effect=OSError):
        assert imp._download_text("http://example.com/x") is None


# ── _check_dataset / _set_dataset / _sqlite_delete (sqlite3 stub) ──


def test_check_dataset_true() -> None:
    """Returns True when meta matches and word count > 0."""
    cur = mock.MagicMock()
    cur.fetchone.side_effect = [("CC-CEDICT",), (5,)]
    with mock.patch("sqlite3.connect") as conn:
        conn.return_value.execute.return_value = cur
        assert imp._check_dataset("zh", "CC-CEDICT") is True


def test_check_dataset_false_meta() -> None:
    """Returns False when meta name mismatches."""
    cur = mock.MagicMock()
    cur.fetchone.side_effect = [("Other",), (5,)]
    with mock.patch("sqlite3.connect") as conn:
        conn.return_value.execute.return_value = cur
        assert imp._check_dataset("zh", "CC-CEDICT") is False


def test_check_dataset_false_count() -> None:
    """Returns False when word count is 0."""
    cur = mock.MagicMock()
    cur.fetchone.side_effect = [("CC-CEDICT",), (0,)]
    with mock.patch("sqlite3.connect") as conn:
        conn.return_value.execute.return_value = cur
        assert imp._check_dataset("zh", "CC-CEDICT") is False


def test_check_dataset_false_none() -> None:
    """Returns False when meta row is missing."""
    cur = mock.MagicMock()
    cur.fetchone.side_effect = [None, (0,)]
    with mock.patch("sqlite3.connect") as conn:
        conn.return_value.execute.return_value = cur
        assert imp._check_dataset("zh", "CC-CEDICT") is False


def test_set_dataset_writes_meta() -> None:
    """_set_dataset writes the meta row and commits."""
    with mock.patch("sqlite3.connect") as conn:
        imp._set_dataset("zh", "CC-CEDICT")
        conn.return_value.execute.assert_called_once()
        conn.return_value.commit.assert_called_once()
        conn.return_value.close.assert_called_once()


def test_sqlite_delete_deletes_lang() -> None:
    """_sqlite_delete deletes by language."""
    with mock.patch("sqlite3.connect") as conn:
        imp._sqlite_delete("zh")
        conn.return_value.execute.assert_called_with(
            "DELETE FROM words WHERE language = ?", ("zh",)
        )
        conn.return_value.commit.assert_called_once()
        conn.return_value.close.assert_called_once()


# ── _parse_pinyin branches ──


def test_parse_pinyin_branches() -> None:
    """_parse_pinyin covers tone/initial/y-w/unknown-final branches."""
    syls = imp._parse_pinyin(["ni3", "hao3"])
    assert [s.attributes["tone"] for s in syls] == ["仄", "仄"]

    assert imp._parse_pinyin(["ma1"])[0].attributes["tone"] == "平"
    assert imp._parse_pinyin(["ma5"])[0].attributes["tone"] == "平"
    assert imp._parse_pinyin(["ni"])[0].attributes["tone"] == ""

    yi = imp._parse_pinyin(["yi3"])[0]
    assert yi.onset == "y"
    assert yi.nucleus == "i"

    y = imp._parse_pinyin(["y"])[0]
    assert y.onset == ""
    assert y.nucleus == ""
    w = imp._parse_pinyin(["w"])[0]
    assert w.onset == ""
    assert w.nucleus == ""

    zh = imp._parse_pinyin(["zhang1"])[0]
    assert zh.onset == "zh"
    assert zh.nucleus == "a"
    assert zh.coda == "ng"

    unknown = imp._parse_pinyin(["xyz"])[0]
    assert unknown.onset == "x"
    assert unknown.nucleus == "yz"


# ── skip when already imported ──


def test_import_skip_when_dataset_present() -> None:
    """All importers return early when the dataset is already present."""
    with mock.patch.object(imp, "_check_dataset", return_value=True):
        imp._import_chinese()
        imp._import_english()
        imp._import_french()
        imp._import_italian()
        imp._import_latin()


def test_import_all_runs_to_completion() -> None:
    """import_all 在数据集已存在时全部走跳过分支（覆盖 508-517 及各 skip return）。

    直接驱动 ``import_all``，确保其在干净环境下也能完整执行（不经 app 后台
    线程且不受网络影响），从而覆盖 import_all 函数体本身。
    """
    with (
        mock.patch.object(imp, "_check_dataset", return_value=True),
        mock.patch.object(imp, "init_db"),
        mock.patch.object(imp, "insert_words") as ins,
    ):
        imp.import_all()
        assert ins.call_count == 0


# ── _import_chinese ──


def _chinese_text() -> str:
    """Build a CC-CEDICT snippet covering every parse branch.

    Returns:
        CC-CEDICT 格式的词典文本。
    """
    lines = [
        "# this is a comment",
        "",
        "onlyone",
        "a b [3]",
        "a b hello",
        "a b",
        "x y [ni3 hao3] [ni3 hao3]",
        "c d [ni3] [hao3]",
        "e f [ma1]",
    ]
    for i in range(1, 502):
        lines.append(f"t{i} s{i} [ni3] /m{i}/")
    return "\n".join(lines)


def test_import_chinese_success() -> None:
    """Chinese import parses lines, flushes batches and persists."""
    text = _chinese_text()
    data = gzip.compress(text.encode("utf-8"))
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", _urlopen_returning(data)),
    ):
        imp._import_chinese()
        assert ins.call_count >= 1
        # 验证至少有一个批次包含正确的 Word 对象
        first_batch = ins.call_args_list[0][0][0]
        assert len(first_batch) >= 1
        assert first_batch[0].language == "zh"
        set_ds.assert_called_once_with("zh", "CC-CEDICT")


def test_import_chinese_oserror() -> None:
    """Chinese import warns and returns on network failure."""
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words"),
        mock.patch.object(imp, "_set_dataset"),
        mock.patch("urllib.request.urlopen", side_effect=OSError),
    ):
        imp._import_chinese()


# ── _import_english ──


def _english_dict() -> dict[str, list[tuple[str, ...]]]:
    """Build CMUdict stub data covering every branch.

    Returns:
        模拟 CMUdict 的字典数据。
    """
    data: dict[str, list[tuple[str, ...]]] = {
        "hello": [("B", "AE1", "T"), ("HH", "EH1", "L", "OW1")],
        "dup": [("B", "AE1", "T"), ("B", "AE1", "T")],
        "novowel": [("X", "Z")],
        "emptyword": [],
        "ab1": [("B", "AE1", "T")],
    }
    for i in range(1, 502):
        data["w" + _alpha(i)] = [("B", "AE1", "T")]
    return data


def _patch_nltk(data: dict[str, list[tuple[str, ...]]]) -> Any:
    """Inject nltk / cmudict stubs; returns a patch context manager.

    Args:
        data: 模拟 CMUdict 的字典数据。

    Returns:
        mock.patch.dict 上下文管理器。
    """
    nltk_mod = types.ModuleType("nltk")
    nltk_mod.data = mock.MagicMock()  # type: ignore[attr-defined]
    nltk_mod.data.find.side_effect = LookupError
    nltk_mod.download = mock.MagicMock()  # type: ignore[attr-defined]
    corpus_mod = types.ModuleType("nltk.corpus")
    cmudict_mod = types.ModuleType("nltk.corpus.cmudict")
    cmudict_mod.dict = mock.MagicMock(return_value=data)  # type: ignore[attr-defined]
    return mock.patch.dict(
        "sys.modules",
        {
            "nltk": nltk_mod,
            "nltk.corpus": corpus_mod,
            "nltk.corpus.cmudict": cmudict_mod,
        },
    )


def test_import_english_success() -> None:
    """English import: multi-pron, dedup, empty-syllable, batch flush, cache."""
    data = _english_dict()
    with (
        _patch_nltk(data),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "set_en_pron") as set_pron,
        mock.patch.object(imp, "_set_dataset") as set_ds,
    ):
        imp._import_english()
        assert ins.call_count >= 1
        # 验证至少有一个批次包含正确的 Word 对象
        first_batch = ins.call_args_list[0][0][0]
        assert len(first_batch) >= 1
        assert first_batch[0].language == "en"
        # 验证 set_en_pron 被调用且包含多发音词
        pron_calls = {c[0][0]: c[0][1] for c in set_pron.call_args_list}
        assert "hello" in pron_calls
        set_ds.assert_called_once_with("en", "CMUdict")


def test_import_english_no_download() -> None:
    """English import does not download when cmudict is already present."""
    data = {"hi": [("HH", "AY1")]}
    nltk_mod = types.ModuleType("nltk")
    nltk_mod.data = mock.MagicMock()  # type: ignore[attr-defined]
    nltk_mod.data.find.return_value = None
    nltk_mod.download = mock.MagicMock()  # type: ignore[attr-defined]
    corpus_mod = types.ModuleType("nltk.corpus")
    cmudict_mod = types.ModuleType("nltk.corpus.cmudict")
    cmudict_mod.dict = mock.MagicMock(return_value=data)  # type: ignore[attr-defined]
    with (
        mock.patch.dict(
            "sys.modules",
            {
                "nltk": nltk_mod,
                "nltk.corpus": corpus_mod,
                "nltk.corpus.cmudict": cmudict_mod,
            },
        ),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words"),
        mock.patch.object(imp, "set_en_pron"),
        mock.patch.object(imp, "_set_dataset"),
    ):
        imp._import_english()
        nltk_mod.download.assert_not_called()


# ── _import_french ──


def _fr_syl(w: str) -> list[Syllable]:
    """Controlled French syllable splitter stub.

    Args:
        w: 待分音节的单词。

    Returns:
        分音节后的 Syllable 列表。
    """
    if w == "we":
        return []
    if w == "wf":
        return [_mk_syl("a")]
    if w == "wg":
        return [_mk_syl("a"), _mk_syl("a"), _mk_syl("a")]
    return [_mk_syl("a")]


def _french_text() -> str:
    """Build a Lexique TSV snippet covering every branch.

    Returns:
        Lexique382 格式的词典文本。
    """
    rows = [
        "junk\tortho\tnbsyl\tphon",
        "onlyone",
        "junk\tw1\t1\tph",
        "junk\t\t1\tph",
        "junk\twa\tabc\tph",
        "junk\twz\t1",
        "junk\twi",
        "junk\twe\t1\tph",
        "junk\twf\t3\tph",
        "junk\twg\t1\tph",
    ]
    for i in range(1, 502):
        rows.append(f"junk\tw{i}\t1\tph{i}")
    return "\n".join(rows)


def test_import_french_success() -> None:
    """French import covers skip/placeholder/truncate branches and flush."""
    fr_instance = mock.MagicMock()
    fr_instance._syllabify_word.side_effect = _fr_syl
    text = _french_text()
    with (
        mock.patch("src.prosody.french.FrenchAnalyzer", return_value=fr_instance),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", _urlopen_returning(text.encode("utf-8"))),
    ):
        imp._import_french()
        assert ins.call_count >= 1
        set_ds.assert_called_once_with("fr", "Lexique382")


def test_import_french_no_text() -> None:
    """French import skips and writes nothing when download fails."""
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", side_effect=OSError),
    ):
        imp._import_french()
        ins.assert_not_called()
        set_ds.assert_not_called()


def test_import_french_header_only() -> None:
    """French import skips data rows when only a header is present."""
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", _urlopen_returning(b"ortho\tnbsyl\tphon")),
    ):
        imp._import_french()
        ins.assert_not_called()
        set_ds.assert_not_called()


# ── _import_italian ──


def _it_syl(w: str) -> list[Syllable]:
    """Controlled Italian syllable splitter stub.

    Args:
        w: 待分音节的单词。

    Returns:
        分音节后的 Syllable 列表。
    """
    if w in ("bb", "fbad"):
        return []
    return [_mk_syl("a")]


def _italian_text() -> str:
    """Build a GLAW-IT XML snippet covering every branch.

    Returns:
        GLAW-IT 格式的词典文本。
    """
    parts = [
        "<txt>pre</txt><title>aa</title><txt>post</txt><title>bb</title>",
        "<title></title>",
        "<title>aa</title>",
    ]
    for i in range(1, 502):
        parts.append(f"<title>t{i}</title>")
    parts.append("<title></title>")
    parts.append('form="fbad"')
    for i in range(1, 502):
        parts.append(f'form="f{i}"')
    parts.append('form=""')
    return "".join(parts)


def test_import_italian_success() -> None:
    """Italian import covers title/gloss/form branches and two flushes."""
    it_instance = mock.MagicMock()
    it_instance._syllabify_word.side_effect = _it_syl
    it_instance._count_syllables_in_word.return_value = 2
    text = _italian_text()
    with (
        mock.patch("src.prosody.italian.ItalianAnalyzer", return_value=it_instance),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", _urlopen_returning(text.encode("utf-8"))),
    ):
        imp._import_italian()
        assert ins.call_count >= 1
        set_ds.assert_called_once_with("it", "GLAW-IT")


def test_import_italian_bz2() -> None:
    """Italian import decompresses raw bz2 payloads."""
    it_instance = mock.MagicMock()
    it_instance._syllabify_word.side_effect = _it_syl
    it_instance._count_syllables_in_word.return_value = 2
    text = _italian_text()
    raw = bz2.compress(text.encode("utf-8"))
    with (
        mock.patch("src.prosody.italian.ItalianAnalyzer", return_value=it_instance),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words"),
        mock.patch.object(imp, "_set_dataset"),
        mock.patch("urllib.request.urlopen", _urlopen_returning(raw)),
    ):
        imp._import_italian()


def test_import_italian_oserror() -> None:
    """Italian import skips and writes nothing on network failure."""
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", side_effect=OSError),
    ):
        imp._import_italian()
        ins.assert_not_called()
        set_ds.assert_not_called()


# ── _import_latin ──


def _la_analyze(clean: str) -> list[Syllable]:
    """Controlled Latin analyzer stub.

    Args:
        clean: 清理后的拉丁文单词。

    Returns:
        分析后的 Syllable 列表。
    """
    if clean == "zzz":
        return []
    return [_mk_syl("a")]


def _latin_text() -> str:
    """Build a Lewis & Short snippet covering every branch.

    Returns:
        Lewis-Short 格式的词典文本。
    """
    lines = [
        "",
        "(comment in parens",
        "1234",
        "hello a definition here",
        "world",
        "dupe foo",
        "dupe foo",
        "zzz",
    ]
    for i in range(1, 502):
        lines.append(f"{_alpha(i)} m{i}")
    return "\n".join(lines)


def test_import_latin_success() -> None:
    """Latin import covers skip/meaning/placeholder branches and flush."""
    la_instance = mock.MagicMock()
    la_instance.analyze_line.side_effect = _la_analyze
    text = _latin_text()
    with (
        mock.patch("src.prosody.latin.LatinAnalyzer", return_value=la_instance),
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", _urlopen_returning(text.encode("utf-8"))),
    ):
        imp._import_latin()
        assert ins.call_count >= 1
        set_ds.assert_called_once_with("la", "Lewis-Short")


def test_import_latin_no_text() -> None:
    """Latin import skips when download fails."""
    with (
        mock.patch.object(imp, "_check_dataset", return_value=False),
        mock.patch.object(imp, "insert_words") as ins,
        mock.patch.object(imp, "_set_dataset") as set_ds,
        mock.patch("urllib.request.urlopen", side_effect=OSError),
    ):
        imp._import_latin()
        ins.assert_not_called()
        set_ds.assert_not_called()
