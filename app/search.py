"""Deterministic keyword search over document chunk metadata on disk."""

from __future__ import annotations

from pathlib import Path

from app.document_index import get_document_index

TEXT_PREVIEW_MAX_CHARS = 240


def _chunk_score(chunk_text: str, tokens: list[str]) -> int:
    """Sum of non-overlapping, case-insensitive substring occurrence counts per token."""
    haystack = chunk_text.lower()
    total = 0
    for tok in tokens:
        total += haystack.count(tok.lower())
    return total


def _safe_preview(text: str, max_chars: int = TEXT_PREVIEW_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def iter_indexable_chunks(
    documents_dir: Path,
) -> list[tuple[str, str, int, str]]:
    """
    Load valid chunks from ``documents_dir`` JSON metadata.

    Returns tuples ``(document_id, original_filename, chunk_index, text)`` in
    filename order, then chunk list order, matching scan semantics used for search.
    """
    index = get_document_index(documents_dir)
    return [
        (row.document_id, row.original_filename, row.chunk_index, row.text)
        for row in index.rows
    ]


def search_documents(documents_dir: Path, query: str, top_k: int) -> list[dict]:
    """
    Scan ``documents_dir`` for ``*.json`` metadata files and rank chunks by keyword score.

    Query is split on whitespace; each token is matched as a case-insensitive substring.
    Results are sorted by descending score, then ``document_id``, then ``chunk_index``.
    """
    q = query.strip()
    tokens = [t for t in q.split() if t]
    if not tokens:
        return []

    matches: list[tuple[int, str, str, int, str]] = []
    index = get_document_index(documents_dir)
    for row in index.rows:
        score = _chunk_score(row.text, tokens)
        if score <= 0:
            continue
        matches.append(
            (
                score,
                row.document_id,
                row.original_filename,
                row.chunk_index,
                row.text,
            )
        )

    matches.sort(key=lambda row: (-row[0], row[1], row[3]))

    out: list[dict] = []
    for score, doc_id, original_filename, idx, text in matches[:top_k]:
        out.append(
            {
                "document_id": doc_id,
                "original_filename": original_filename,
                "chunk_index": idx,
                "score": score,
                "text_preview": _safe_preview(text),
            }
        )
    return out
