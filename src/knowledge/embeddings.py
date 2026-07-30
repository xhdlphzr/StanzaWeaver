# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import numpy as np

_MODEL = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def rerank(query: str, candidates: list[dict], top_k: int = 20) -> list[dict]:
    if not query or not candidates:
        return candidates
    try:
        model = _get_model()
        texts = [c["text"] for c in candidates]
        query_emb = model.encode([query], normalize_embeddings=True)[0]
        doc_embs = model.encode(texts, normalize_embeddings=True)
        scores = np.dot(doc_embs, query_emb)
        for c, score in zip(candidates, scores):
            c["_score"] = float(score)
        candidates.sort(key=lambda c: c.get("_score", 0), reverse=True)
    except Exception:
        pass
    return candidates[:top_k]
