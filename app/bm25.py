"""Okapi BM25 over chunk text from the same on-disk JSON metadata as keyword search."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from app.search import TEXT_PREVIEW_MAX_CHARS, _safe_preview, iter_indexable_chunks

# Fixed hyperparameters for deterministic scores across runs.
K1 = 1.2
B = 0.75
EPS = 1e-9

# English words and digits; CJK: one codepoint per token (no segmentation).
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Conservative tokenization: ASCII alnum words (lower-cased) + one Han character per token."""
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_PATTERN.finditer(text):
        s = m.group(0)
        if s.isascii():
            out.append(s.lower())
        else:
            out.extend(list(s))
    return out


def _bm25_idf(n_docs: int, df: int) -> float:
    # Okapi: log((N - df + 0.5) / (df + 0.5) + 1)
    return math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)


def _bm25_term_score(tf: int, len_d: int, avgdl: float, idf: float) -> float:
    if tf <= 0 or idf <= 0:
        return 0.0
    denom = tf + K1 * (1.0 - B + B * (len_d / avgdl))
    return idf * (tf * (K1 + 1.0)) / denom


def search_documents_bm25(documents_dir: Path, query: str, top_k: int) -> list[dict]:
    """
    Rank chunks with BM25; same JSON inputs as keyword search, ties broken by
    ``document_id`` then ``chunk_index`` ascending.
    """
    q = query.strip()
    q_tokens = tokenize(q)
    if not q_tokens or top_k <= 0:
        return []

    if not documents_dir.is_dir():
        return []

    rows: list[tuple[str, str, int, str]] = list(iter_indexable_chunks(documents_dir))
    n_docs = len(rows)
    if n_docs == 0:
        return []

    doc_tokens: list[list[str]] = [tokenize(text) for _, _, _, text in rows]
    lens = [len(dt) for dt in doc_tokens]
    avgdl = (sum(lens) / n_docs) if n_docs else 0.0
    if avgdl < EPS:
        avgdl = 1.0

    df_map: dict[str, int] = {}
    for dt in doc_tokens:
        for t in set(dt):
            df_map[t] = df_map.get(t, 0) + 1

    idf: dict[str, float] = {
        t: _bm25_idf(n_docs, dfc) for t, dfc in df_map.items() if dfc > 0
    }

    q_freq = Counter(q_tokens)
    scores: list[tuple[float, str, str, int, str]] = []
    for i, (doc_id, oname, idx, text) in enumerate(rows):
        dt = doc_tokens[i]
        tf = Counter(dt)
        len_d = lens[i] or 1
        s = 0.0
        for qterm, q_w in q_freq.items():
            idf_t = idf.get(qterm, 0.0)
            if idf_t <= 0.0:
                continue
            tfn = tf.get(qterm, 0)
            if tfn == 0:
                continue
            s += q_w * _bm25_term_score(tfn, len_d, avgdl, idf_t)
        if s > 0.0:
            scores.append((s, doc_id, oname, idx, text))

    scores.sort(key=lambda r: (-r[0], r[1], r[3]))

    out: list[dict] = []
    for s, doc_id, original_filename, cidx, text in scores[:top_k]:
        out.append(
            {
                "document_id": doc_id,
                "original_filename": original_filename,
                "chunk_index": cidx,
                "score": s,
                "text_preview": _safe_preview(text, TEXT_PREVIEW_MAX_CHARS),
            }
        )
    return out
