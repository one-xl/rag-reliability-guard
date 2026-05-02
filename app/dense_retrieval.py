"""Dense (embedding-based) and hybrid retrieval using sentence-transformers + FAISS."""

from __future__ import annotations

import logging
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.document_index import DocumentIndex, get_document_index
from app.search import TEXT_PREVIEW_MAX_CHARS, _safe_preview

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict[str, SentenceTransformer] = {}
_index_cache: dict[tuple, tuple[faiss.IndexFlatIP, list[str]]] = {}


def _get_model(model_name: str = DEFAULT_MODEL_NAME) -> SentenceTransformer:
    if model_name not in _model_cache:
        logger.info("Loading sentence-transformers model: %s", model_name)
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def _encode_texts(
    texts: list[str],
    model_name: str = DEFAULT_MODEL_NAME,
    batch_size: int = 64,
) -> np.ndarray:
    model = _get_model(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return np.ascontiguousarray(embeddings, dtype=np.float32)


def _build_dense_index(
    index: DocumentIndex,
    model_name: str = DEFAULT_MODEL_NAME,
) -> tuple[faiss.IndexFlatIP, list[str]]:
    texts = [row.text for row in index.rows]
    if not texts:
        dim = 384
        empty_index = faiss.IndexFlatIP(dim)
        return empty_index, []
    embeddings = _encode_texts(texts, model_name)
    dim = embeddings.shape[1]
    faiss_index = faiss.IndexFlatIP(dim)
    faiss_index.add(embeddings)
    return faiss_index, texts


def get_dense_index(
    documents_dir: Path,
    model_name: str = DEFAULT_MODEL_NAME,
) -> tuple[faiss.IndexFlatIP, DocumentIndex]:
    index = get_document_index(documents_dir)
    cache_key = (documents_dir.resolve(), model_name)
    cached = _index_cache.get(cache_key)
    if cached is not None:
        faiss_index, cached_texts = cached
        current_texts = [row.text for row in index.rows]
        if cached_texts == current_texts:
            return faiss_index, index
    faiss_index, texts = _build_dense_index(index, model_name)
    _index_cache[cache_key] = (faiss_index, texts)
    return faiss_index, index


def refresh_dense_index(documents_dir: Path, model_name: str = DEFAULT_MODEL_NAME) -> None:
    cache_key = (documents_dir.resolve(), model_name)
    _index_cache.pop(cache_key, None)


def search_documents_dense(
    documents_dir: Path,
    query: str,
    top_k: int,
    model_name: str = DEFAULT_MODEL_NAME,
) -> list[dict]:
    q = query.strip()
    if not q or top_k <= 0:
        return []

    faiss_index, index = get_dense_index(documents_dir, model_name)
    n_rows = len(index.rows)
    if n_rows == 0:
        return []

    q_emb = _encode_texts([q], model_name)
    k = min(top_k, n_rows)
    scores, indices = faiss_index.search(q_emb, k)

    out: list[dict] = []
    for score, idx in zip(scores[0], indices[0], strict=False):
        if idx < 0 or idx >= n_rows:
            continue
        row = index.rows[idx]
        out.append({
            "document_id": row.document_id,
            "original_filename": row.original_filename,
            "chunk_index": row.chunk_index,
            "score": float(score),
            "text_preview": _safe_preview(row.text, TEXT_PREVIEW_MAX_CHARS),
        })
    return out


def search_documents_hybrid(
    documents_dir: Path,
    query: str,
    top_k: int,
    alpha: float = 0.5,
    model_name: str = DEFAULT_MODEL_NAME,
) -> list[dict]:
    from app.bm25 import search_documents_bm25

    q = query.strip()
    if not q or top_k <= 0:
        return []

    bm25_results = search_documents_bm25(documents_dir, q, top_k=top_k * 2)
    dense_results = search_documents_dense(documents_dir, q, top_k=top_k * 2, model_name=model_name)

    def _normalize(results: list[dict]) -> dict[tuple[str, int], float]:
        if not results:
            return {}
        max_score = max(r["score"] for r in results)
        if max_score < 1e-9:
            max_score = 1.0
        return {
            (r["document_id"], r["chunk_index"]): r["score"] / max_score
            for r in results
        }

    bm25_norm = _normalize(bm25_results)
    dense_norm = _normalize(dense_results)

    all_keys = set(bm25_norm.keys()) | set(dense_norm.keys())
    combined: list[tuple[float, str, int, str, str, float, float]] = []

    bm25_lookup = {(r["document_id"], r["chunk_index"]): r for r in bm25_results}
    dense_lookup = {(r["document_id"], r["chunk_index"]): r for r in dense_results}

    for key in all_keys:
        bm25_s = bm25_norm.get(key, 0.0)
        dense_s = dense_norm.get(key, 0.0)
        hybrid_s = alpha * bm25_s + (1 - alpha) * dense_s
        ref = bm25_lookup.get(key) or dense_lookup.get(key)
        if ref is None:
            continue
        combined.append((
            hybrid_s,
            ref["document_id"],
            ref["chunk_index"],
            ref["original_filename"],
            ref["text_preview"],
            bm25_s,
            dense_s,
        ))

    combined.sort(key=lambda r: (-r[0], r[1], r[2]))

    out: list[dict] = []
    for hybrid_s, doc_id, cidx, fname, preview, bm25_s, dense_s in combined[:top_k]:
        out.append({
            "document_id": doc_id,
            "original_filename": fname,
            "chunk_index": cidx,
            "score": round(hybrid_s, 6),
            "bm25_score": round(bm25_s, 6),
            "dense_score": round(dense_s, 6),
            "text_preview": preview,
        })
    return out
