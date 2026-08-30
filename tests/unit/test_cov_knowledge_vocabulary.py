# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""src.knowledge.vocabulary 的 100% 行覆盖补全测试。

使用临时文件型 SQLite 数据库（经 ``set_db_path`` 注入），不触碰任何
真实磁盘库或网络；``rerank`` 通过 patch 替换以避免加载嵌入模型。
"""

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.knowledge import embeddings
from src.knowledge.vocabulary import (
    _syl_from_json,
    _syl_matches,
    get_en_pron,
    has_words,
    insert_word,
    insert_words,
    search_words,
    set_db_path,
    set_en_pron,
    word_count,
)
from src.models.syllable import Syllable
from src.models.word import Word


@pytest.fixture
def vocab_db(tmp_path: Path) -> Path:
    """创建空词库并返回数据库路径。

    Returns:
        临时 SQLite 数据库文件路径。
    """
    from src.knowledge.vocabulary import init_db

    db_file = tmp_path / "vocab.db"
    set_db_path(db_file)
    init_db()
    # 清空任何可能残留/外部导入的数据，保证测试基于空库（与环境词库无关）
    conn = sqlite3.connect(str(db_file))
    conn.execute("DELETE FROM words")
    conn.execute("DELETE FROM en_pron")
    conn.commit()
    conn.close()
    return db_file


def test_set_db_path_overrides_path(tmp_path: Path) -> None:
    """验证 set_db_path 写入全局数据库路径（line 31）。"""
    custom = tmp_path / "custom_vocab.db"
    set_db_path(custom)
    from src.knowledge.vocabulary import get_db_path

    assert get_db_path() == custom


def test_insert_word_delegates_to_insert_words(tmp_path: Path) -> None:
    """验证 insert_word 委托 insert_words（line 71）。"""
    from src.knowledge.vocabulary import init_db

    set_db_path(tmp_path / "insert_one.db")
    init_db()
    w = Word(
        text="DO",
        language="en",
        syllables=[Syllable(onset="d", nucleus="ow")],
        meaning="做",
    )
    insert_word(w)
    assert word_count("en") == 1


def test_insert_words_with_and_without_syllables(vocab_db: Path) -> None:
    """验证批量插入同时覆盖有/无音节两条分支（lines 80-96）。"""
    with_syl = Word(
        text="CAT",
        language="en",
        syllables=[Syllable(onset="k", nucleus="ae", coda="t")],
        meaning="猫",
    )
    without_syl = Word(text="HELLO", language="en", syllables=[], meaning="你好")
    insert_words([with_syl, without_syl])
    assert word_count("en") == 2


def test_syl_from_json_keeps_dict_attributes() -> None:
    """验证 _syl_from_json 正常还原属性（lines 108-111 正常分支）。"""
    s = _syl_from_json(
        {
            "onset": "zh",
            "nucleus": "a",
            "coda": "ng",
            "attributes": {"tone": "平", "stress": "heavy", "length": "long"},
        }
    )
    assert s.onset == "zh"
    assert s.attributes["tone"] == "平"


def test_syl_from_json_non_dict_attributes() -> None:
    """验证 _syl_from_json 当 attributes 非字典时回退（lines 109-111）。"""
    s = _syl_from_json({"onset": "b", "nucleus": "a", "coda": "t", "attributes": "bad"})
    assert s.attributes == {"tone": "", "stress": "", "length": ""}


def test_syl_matches_all_branches() -> None:
    """逐分支覆盖 _syl_matches（lines 141-151）。"""
    s = Syllable(
        onset="k",
        nucleus="ae",
        coda="t",
        attributes={"tone": "1", "stress": "heavy", "length": "long"},
    )
    # 无约束
    assert _syl_matches(s)
    # onset 匹配 / 不匹配
    assert _syl_matches(s, onset="k")
    assert not _syl_matches(s, onset="x")
    # nucleus 匹配 / 不匹配
    assert _syl_matches(s, nucleus="ae")
    assert not _syl_matches(s, nucleus="ow")
    # coda 匹配 / 不匹配
    assert _syl_matches(s, coda="t")
    assert not _syl_matches(s, coda="ng")
    # tone 匹配 / 不匹配
    assert _syl_matches(s, tone="1")
    assert not _syl_matches(s, tone="9")
    # stress 匹配 / 不匹配
    assert _syl_matches(s, stress="heavy")
    assert not _syl_matches(s, stress="light")
    # length 匹配 / 不匹配
    assert _syl_matches(s, length="long")
    assert not _syl_matches(s, length="short")


def test_search_no_constraints(vocab_db: Path) -> None:
    """无约束搜索：覆盖主体循环与音节重建（lines 181-237 部分）。"""
    insert_words(
        [
            Word(
                text="CAT",
                language="en",
                syllables=[Syllable(onset="k", nucleus="ae", coda="t")],
                meaning="猫",
            ),
            Word(text="HELLO", language="en", syllables=[], meaning="你好"),
        ]
    )
    results = search_words("en", limit=20)
    texts = {r["text"] for r in results}
    assert texts == {"CAT", "HELLO"}
    # HELLO 无音节 -> 重建占位音节
    hello = next(r for r in results if r["text"] == "HELLO")
    assert hello["syllables"][0]["nucleus"] == "?"


def test_search_empty_syllables_json_branch(vocab_db: Path) -> None:
    """覆盖 syls_json 为空串的 else 分支（line 230）。"""
    conn = sqlite3.connect(str(vocab_db))
    conn.execute(
        "INSERT INTO words (text, language, meaning, syllables_json, "
        "syllable_count) VALUES (?, ?, ?, ?, ?)",
        ("EMPTY", "en", "空", "", 2),
    )
    conn.commit()
    conn.close()
    results = search_words("en", limit=10)
    empty = next(r for r in results if r["text"] == "EMPTY")
    assert len(empty["syllables"]) == 2
    assert empty["syllables"][0]["nucleus"] == "?"


def test_search_with_syllable_count(vocab_db: Path) -> None:
    """覆盖 syllable_count 约束分支（lines 185-187）。"""
    insert_words(
        [
            Word(
                text="CAT",
                language="en",
                syllables=[Syllable(onset="k", nucleus="ae")],
                meaning="猫",
            ),
            Word(
                text="DOG",
                language="en",
                syllables=[
                    Syllable(onset="d", nucleus="aw"),
                    Syllable(onset="g", nucleus="ee"),
                ],
                meaning="狗",
            ),
        ]
    )
    one_syl = search_words("en", syllable_count=1, limit=10)
    assert {r["text"] for r in one_syl} == {"CAT"}


def test_search_all_constraints_match_and_skip(vocab_db: Path) -> None:
    """覆盖全部逐位约束构造分支及匹配/跳过（lines 189-246）。"""
    insert_words(
        [
            Word(
                text="MATCH",
                language="en",
                syllables=[
                    Syllable(
                        onset="k",
                        nucleus="ae",
                        coda="t",
                        attributes={
                            "tone": "1",
                            "stress": "heavy",
                            "length": "long",
                        },
                    )
                ],
                meaning="匹配",
            ),
            Word(
                text="NOMATCH",
                language="en",
                syllables=[
                    Syllable(
                        onset="d",
                        nucleus="ow",
                        coda="g",
                        attributes={
                            "tone": "2",
                            "stress": "light",
                            "length": "short",
                        },
                    )
                ],
                meaning="不匹配",
            ),
        ]
    )
    results = search_words(
        "en",
        onset="k",
        nucleus="ae",
        coda="t",
        tone="1",
        stress="heavy",
        length="long",
        limit=10,
    )
    assert len(results) == 1
    assert results[0]["text"] == "MATCH"
    assert results[0]["matched_syllable"] == 0


def test_search_limit_break(vocab_db: Path) -> None:
    """覆盖达到 limit 后中断的循环分支（lines 257-258）。"""
    insert_words(
        [
            Word(
                text="A",
                language="en",
                syllables=[Syllable(onset="k", nucleus="a")],
            ),
            Word(
                text="B",
                language="en",
                syllables=[Syllable(onset="k", nucleus="b")],
            ),
        ]
    )
    results = search_words("en", onset="k", limit=1)
    assert len(results) == 1


def test_search_with_query_rerank(vocab_db: Path) -> None:
    """覆盖 query 非空时调用 rerank 的分支（lines 260-264）。"""
    insert_words(
        [
            Word(
                text="CAT",
                language="en",
                syllables=[Syllable(onset="k", nucleus="ae")],
                meaning="猫",
            )
        ]
    )
    fake: list[dict[str, Any]] = [
        {
            "text": "CAT",
            "language": "en",
            "meaning": "猫",
            "syllables": [],
            "matched_syllable": None,
        }
    ]
    with patch.object(embeddings, "rerank", return_value=fake) as mock_rerank:
        results = search_words("en", query="animal", limit=10)
    mock_rerank.assert_called_once()
    assert results == fake


def test_search_query_no_results_skips_rerank(vocab_db: Path) -> None:
    """覆盖 query 非空但无结果时不调用 rerank（line 260 假分支）。"""
    with patch.object(embeddings, "rerank") as mock_rerank:
        results = search_words("en", query="animal", limit=10)
    mock_rerank.assert_not_called()
    assert results == []


def test_word_count_and_has_words(vocab_db: Path) -> None:
    """覆盖 word_count 两个分支及 has_words（lines 276-284, 296）。"""
    insert_words(
        [Word(text="CAT", language="en", syllables=[Syllable(onset="k", nucleus="ae")])]
    )
    assert word_count() == 1
    assert word_count("en") == 1
    assert word_count("zh") == 0
    assert has_words("en")
    assert not has_words("zh")


def test_en_pron_roundtrip_and_missing(vocab_db: Path) -> None:
    """覆盖 set_en_pron / get_en_pron 全部分支（lines 306-312, 331-332）。"""
    set_en_pron("cat", [["K", "AE", "T"], ["K", "AH", "T"]])
    data = get_en_pron("cat")
    assert data == [["K", "AE", "T"], ["K", "AH", "T"]]
    assert get_en_pron("nonexistent") is None


def test_get_db_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 _DB_PATH 为 None 时回退到默认路径（line 42）。"""
    from src.knowledge import vocabulary

    monkeypatch.setattr(vocabulary, "_DB_PATH", None)
    assert vocabulary.get_db_path() == (
        Path.home() / ".stanza_weaver" / "vocabulary.db"
    )
