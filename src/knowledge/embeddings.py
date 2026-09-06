# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""词条向量重排。

用 sentence-transformers 多语言模型对候选词按语义相似度排序；
模型未就绪或离线时静默降级为原顺序。

不依赖 numpy：``encode(normalize_embeddings=True)`` 已输出归一化向量，
相似度用纯 Python 点积计算即可（也避免引入重数值依赖）。
"""

from typing import Any

_MODEL: Any = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model() -> Any:
    """惰性加载嵌入模型（仅首次调用时加载）。

    Returns:
        SentenceTransformer 实例（或任意具备 encode 的对象）。
    """
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def _to_float_list(vec: Any) -> list[float]:
    """把 encode 返回的向量（numpy 数组或可迭代序列）转为 float 列表。

    Args:
        vec: 单条向量。

    Returns:
        float 列表。
    """
    return [float(x) for x in vec]


def rerank(
    query: str, candidates: list[dict[str, Any]], top_k: int = 20
) -> list[dict[str, Any]]:
    """按语义相似度重排候选词。

    Args:
        query: 查询文本。
        candidates: 候选词字典列表。
        top_k: 返回数量。

    Returns:
        重排后的列表（失败时保持原顺序）。
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
    except Exception:  # noqa: S110, BLE001 - 模型加载/编码失败时静默降级为原顺序
        pass
    return candidates[:top_k]
