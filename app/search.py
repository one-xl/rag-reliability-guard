"""Deterministic keyword search over document chunk metadata on disk."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

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

    if not documents_dir.is_dir():
        return []

    matches: list[tuple[int, str, str, int, str]] = []
    for path in sorted(documents_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        doc_id = raw.get("id")
        original_filename = raw.get("original_filename")
        chunks = raw.get("chunks")
        if not isinstance(doc_id, str) or not isinstance(original_filename, str):
            continue
        if not isinstance(chunks, list):
            continue

        try:
            uuid.UUID(doc_id)
        except ValueError:
            continue

        for ch in chunks:
            if not isinstance(ch, dict):
                continue
            text = ch.get("text")
            idx = ch.get("index")
            if not isinstance(text, str) or not isinstance(idx, int):
                continue
            score = _chunk_score(text, tokens)
            if score <= 0:
                continue
            matches.append((score, doc_id, original_filename, idx, text))

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
