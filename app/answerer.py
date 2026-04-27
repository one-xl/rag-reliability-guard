"""Extractive answer drafting from retrieved evidence chunks."""

from __future__ import annotations

from pathlib import Path

from app.bm25 import search_documents_bm25
from app.llm_client import generate_doubao_answer
from app.search import search_documents

VALID_METHODS = {"keyword", "bm25"}
VALID_GENERATORS = {"extractive", "doubao"}


def retrieve_for_method(documents_dir: Path, question: str, top_k: int, method: str) -> list[dict]:
    if method == "keyword":
        return search_documents(documents_dir, question, top_k)
    if method == "bm25":
        return search_documents_bm25(documents_dir, question, top_k)
    raise ValueError("method must be keyword or bm25")


def draft_answer(
    question: str,
    documents_dir: Path,
    top_k: int = 5,
    method: str = "keyword",
    generator: str = "extractive",
) -> dict:
    """Return a citation-bearing answer using extractive evidence or Doubao generation."""
    stripped = question.strip()
    if not stripped:
        raise ValueError("question must be a non-empty string")
    if method not in VALID_METHODS:
        raise ValueError("method must be keyword or bm25")
    if generator not in VALID_GENERATORS:
        raise ValueError("generator must be extractive or doubao")
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    results = retrieve_for_method(documents_dir, stripped, top_k, method)
    citations = [
        {
            "index": i + 1,
            "document_id": result["document_id"],
            "original_filename": result["original_filename"],
            "chunk_index": result["chunk_index"],
            "score": result["score"],
            "text_preview": result["text_preview"],
        }
        for i, result in enumerate(results)
    ]

    if not citations:
        return {
            "question": stripped,
            "method": method,
            "generator": generator,
            "top_k": top_k,
            "answer": "知识库中没有检索到足够信息，暂时无法回答该问题。",
            "citations": [],
        }

    if generator == "doubao":
        answer = generate_doubao_answer(stripped, citations)
        return {
            "question": stripped,
            "method": method,
            "generator": generator,
            "top_k": top_k,
            "answer": answer,
            "citations": citations,
        }

    evidence_lines = [
        f"[{citation['index']}] {citation['text_preview']}" for citation in citations
    ]
    answer = "根据知识库中检索到的证据，可以参考以下内容：\n" + "\n".join(
        evidence_lines
    )
    return {
        "question": stripped,
        "method": method,
        "generator": generator,
        "top_k": top_k,
        "answer": answer,
        "citations": citations,
    }
