# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Entry vector reranking.

Rank candidate words by semantic similarity with a multilingual
sentence-transformers model; degrade silently to the original order when the
model is unavailable or offline.

No numpy dependency: ``encode(normalize_embeddings=True)`` already returns
normalized vectors, so pure-Python dot products are enough (and avoid pulling in
heavy numeric dependencies).
"""

from typing import Any

_MODEL: Any = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model() -> Any:
    """Load the embedding model lazily (only on the first call).

    Returns:
        SentenceTransformer instance (or any object exposing ``encode``).

    """
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def _to_float_list(vec: Any) -> list[float]:
    """Convert a vector to a list of floats.

    Accepts the numpy array or iterable returned by ``encode``.

    Args:
        vec: A single vector.

    Returns:
        A list of floats.

    """
    return [float(x) for x in vec]


def rerank(
    query: str, candidates: list[dict[str, Any]], top_k: int = 20
) -> list[dict[str, Any]]:
    """Rerank candidate words by semantic similarity.

    Args:
        query: Query text.
        candidates: List of candidate word dictionaries.
        top_k: Number of results to return.

    Returns:
        Reranked list (keeps the original order on failure).

    """
    if not query or not candidates:
        return candidates
    try:
        model = _get_model()
        texts = [str(c["text"]) for c in candidates]
        query_vec = _to_float_list(model.encode([query], normalize_embeddings=True)[0])
        doc_rows = model.encode(texts, normalize_embeddings=True)
        for c, row in zip(candidates, doc_rows):
            vec = _to_float_list(row)
            c["_score"] = sum(a * b for a, b in zip(query_vec, vec))
        candidates.sort(key=lambda c: float(c.get("_score", 0)), reverse=True)
    except Exception:  # noqa: S110, BLE001 - keep the original order on failure
        pass
    return candidates[:top_k]
