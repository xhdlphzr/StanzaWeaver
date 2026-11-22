# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Line-coverage tests for the embedding reranker (src.knowledge.embeddings)."""

import sys
from unittest.mock import MagicMock, patch

from src.knowledge import embeddings


class _FakeModel:
    """Lightweight fake model that replaces SentenceTransformer.

    Returns a fixed vector for a single query and distinguishable vectors
    for multiple documents, making similarity ordering assertable.
    """

    def encode(
        self, texts: list[str], normalize_embeddings: bool = False
    ) -> list[list[float]]:
        """Return query or document vectors based on input length.

        Args:
            texts: Texts to encode.
            normalize_embeddings: Whether to normalize (ignored here).

        Returns:
            Two-dimensional float list of shape (len(texts), 2).

        """
        if len(texts) == 1:
            return [[1.0, 0.0]]
        return [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]


def test_rerank_empty_query_returns_candidates() -> None:
    """Verify an empty query returns the original candidates (lines 45-46)."""
    candidates = [{"text": "a"}, {"text": "b"}]
    assert embeddings.rerank("", candidates) == candidates


def test_rerank_empty_candidates_returns_candidates() -> None:
    """Verify an empty candidate list returns as-is (lines 45-46)."""
    assert embeddings.rerank("query", []) == []


def test_rerank_sorts_by_similarity_and_sets_scores() -> None:
    """Verify the normal path reranks by similarity and writes _score."""
    candidates = [
        {"text": "doc_b"},
        {"text": "doc_a"},
        {"text": "doc_c"},
    ]
    fake = _FakeModel()
    with patch.object(embeddings, "_get_model", return_value=fake):
        result = embeddings.rerank("query", candidates)
    # Similarity: [1, 0, 0.5] -> order doc_b(1.0), doc_c(0.5), doc_a(0)
    assert [c["text"] for c in result] == ["doc_b", "doc_c", "doc_a"]
    assert result[0]["_score"] == 1.0
    assert result[1]["_score"] == 0.5
    assert result[2]["_score"] == 0.0


def test_rerank_respects_top_k() -> None:
    """Verify results are truncated to top_k."""
    candidates = [{"text": f"d{i}"} for i in range(5)]
    fake = _FakeModel()
    with patch.object(embeddings, "_get_model", return_value=fake):
        result = embeddings.rerank("query", candidates, top_k=2)
    assert len(result) == 2


def test_rerank_model_failure_silent_fallback() -> None:
    """Verify model load/encode errors silently fall back to original order."""
    candidates = [{"text": "a"}, {"text": "b"}]
    with patch.object(embeddings, "_get_model", side_effect=RuntimeError("boom")):
        result = embeddings.rerank("query", candidates)
    assert result == candidates


def test_get_model_loads_once_and_caches() -> None:
    """Verify _get_model loads only on the first call and reuses the cache."""
    from types import SimpleNamespace

    fake_st = MagicMock()
    fake_module = SimpleNamespace(SentenceTransformer=fake_st)
    prev = embeddings._MODEL
    with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
        embeddings._MODEL = None
        try:
            model1 = embeddings._get_model()
            model2 = embeddings._get_model()
        finally:
            embeddings._MODEL = prev
    assert model1 is model2
    assert model1 is fake_st.return_value
    fake_st.assert_called_once_with(embeddings._MODEL_NAME)
