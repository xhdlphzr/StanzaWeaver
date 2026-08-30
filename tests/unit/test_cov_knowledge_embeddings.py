# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""词条向量重排模块（src.knowledge.embeddings）的 100% 行覆盖测试。"""

from unittest.mock import patch

import numpy as np
from numpy.typing import NDArray

from src.knowledge import embeddings


class _FakeModel:
    """用于替换 SentenceTransformer 的轻量假模型。

    对单条查询返回固定向量，对多篇文档返回可区分的向量，
    使相似度排序可被断言。
    """

    def encode(
        self, texts: list[str], normalize_embeddings: bool = False
    ) -> NDArray[np.float64]:
        """根据输入长度返回查询或文档向量（忽略归一化参数）。

        Args:
            texts: 待编码文本列表。
            normalize_embeddings: 是否归一化（此处不生效）。

        Returns:
            二维 numpy 数组，形状为 (len(texts), 2)。
        """
        if len(texts) == 1:
            return np.array([[1.0, 0.0]], dtype=np.float64)
        return np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float64)


def test_rerank_empty_query_returns_candidates() -> None:
    """空查询时直接返回原候选列表（line 45-46）。"""
    candidates = [{"text": "a"}, {"text": "b"}]
    assert embeddings.rerank("", candidates) == candidates


def test_rerank_empty_candidates_returns_candidates() -> None:
    """空候选列表时直接返回原候选列表（line 45-46）。"""
    assert embeddings.rerank("query", []) == []


def test_rerank_sorts_by_similarity_and_sets_scores() -> None:
    """正常路径：按语义相似度重排并写入 _score（line 48-55, 58）。"""
    candidates = [
        {"text": "doc_b"},
        {"text": "doc_a"},
        {"text": "doc_c"},
    ]
    fake = _FakeModel()
    with patch.object(embeddings, "_get_model", return_value=fake):
        result = embeddings.rerank("query", candidates)
    # 相似度：[1,0,0.5] -> 顺序应为 doc_b(1.0), doc_c(0.5), doc_a(0)
    assert [c["text"] for c in result] == ["doc_b", "doc_c", "doc_a"]
    assert result[0]["_score"] == 1.0
    assert result[1]["_score"] == 0.5
    assert result[2]["_score"] == 0.0


def test_rerank_respects_top_k() -> None:
    """结果按 top_k 截断（line 58）。"""
    candidates = [{"text": f"d{i}"} for i in range(5)]
    fake = _FakeModel()
    with patch.object(embeddings, "_get_model", return_value=fake):
        result = embeddings.rerank("query", candidates, top_k=2)
    assert len(result) == 2


def test_rerank_model_failure_silent_fallback() -> None:
    """模型加载/编码异常时静默降级为原顺序（line 56-57）。"""
    candidates = [{"text": "a"}, {"text": "b"}]
    with patch.object(embeddings, "_get_model", side_effect=RuntimeError("boom")):
        result = embeddings.rerank("query", candidates)
    assert result == candidates


def test_get_model_loads_once_and_caches() -> None:
    """_get_model 仅在首次调用时加载模型，之后复用缓存（line 24-29）。"""
    with patch("sentence_transformers.SentenceTransformer") as st_mock:
        embeddings._MODEL = None
        model1 = embeddings._get_model()
        model2 = embeddings._get_model()
    assert model1 is model2
    st_mock.assert_called_once_with(embeddings._MODEL_NAME)
