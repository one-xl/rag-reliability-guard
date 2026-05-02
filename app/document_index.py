"""Small in-memory index over document metadata JSON files."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.tokenization import tokenize


@dataclass(frozen=True)
class IndexRow:
    document_id: str
    original_filename: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class DocumentIndex:
    rows: tuple[IndexRow, ...]
    text_by_key: dict[tuple[str, int], str]
    doc_tokens: tuple[tuple[str, ...], ...]
    doc_token_counts: tuple[Counter[str], ...]
    doc_lengths: tuple[int, ...]
    avg_doc_length: float
    document_frequency: dict[str, int]
    state: tuple[tuple[str, int, int], ...]


_CACHE: dict[Path, DocumentIndex] = {}


def _metadata_state(documents_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not documents_dir.is_dir():
        return ()
    state: list[tuple[str, int, int]] = []
    for path in sorted(documents_dir.glob("*.json")):
        try:
            stat = path.stat()
        except OSError:
            continue
        state.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(state)


def _load_rows(documents_dir: Path) -> tuple[IndexRow, ...]:
    if not documents_dir.is_dir():
        return ()

    rows: list[IndexRow] = []
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

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("text")
            index = chunk.get("index")
            if not isinstance(text, str) or not isinstance(index, int):
                continue
            rows.append(IndexRow(doc_id, original_filename, index, text))
    return tuple(rows)


def _build_index(documents_dir: Path, state: tuple[tuple[str, int, int], ...]) -> DocumentIndex:
    rows = _load_rows(documents_dir)
    doc_tokens = tuple(tuple(tokenize(row.text)) for row in rows)
    doc_token_counts = tuple(Counter(tokens) for tokens in doc_tokens)
    doc_lengths = tuple(len(tokens) for tokens in doc_tokens)
    avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1.0

    document_frequency: dict[str, int] = {}
    for tokens in doc_tokens:
        for token in set(tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    return DocumentIndex(
        rows=rows,
        text_by_key={(row.document_id, row.chunk_index): row.text for row in rows},
        doc_tokens=doc_tokens,
        doc_token_counts=doc_token_counts,
        doc_lengths=doc_lengths,
        avg_doc_length=avg_doc_length,
        document_frequency=document_frequency,
        state=state,
    )


def get_document_index(documents_dir: Path) -> DocumentIndex:
    """Return a cached index, rebuilding when metadata file state changes."""
    key = documents_dir.resolve()
    state = _metadata_state(documents_dir)
    cached = _CACHE.get(key)
    if cached is not None and cached.state == state:
        return cached
    index = _build_index(documents_dir, state)
    _CACHE[key] = index
    return index


def refresh_document_index(documents_dir: Path) -> DocumentIndex:
    """Force rebuild after known writes such as document upload."""
    key = documents_dir.resolve()
    _CACHE.pop(key, None)
    return get_document_index(documents_dir)
