"""Retrieval evaluation helpers for small local benchmark cases."""

from __future__ import annotations

from pathlib import Path

from app.search import search_documents


def _validate_case(case: dict, index: int) -> None:
    question = case.get("question")
    answerable = case.get("answerable")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"case {index}: question must be a non-empty string")
    if not isinstance(answerable, bool):
        raise ValueError(f"case {index}: answerable must be a boolean")

    if answerable:
        has_doc = isinstance(case.get("expected_document_id"), str)
        has_chunk = isinstance(case.get("expected_chunk_index"), int)
        if not has_doc and not has_chunk:
            raise ValueError(
                f"case {index}: answerable cases need expected_document_id or expected_chunk_index"
            )


def _matches_expected(result: dict, case: dict) -> bool:
    expected_doc = case.get("expected_document_id")
    expected_chunk = case.get("expected_chunk_index")
    if expected_doc is not None and result.get("document_id") != expected_doc:
        return False
    if expected_chunk is not None and result.get("chunk_index") != expected_chunk:
        return False
    return True


def evaluate_retrieval(cases: list[dict], documents_dir: Path, top_k: int) -> dict:
    """Evaluate Recall@K for answerable cases and empty-result accuracy for unanswerable ones."""
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    answerable_total = 0
    answerable_hits = 0
    not_answerable_total = 0
    empty_result_hits = 0

    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {i}: must be an object")
        _validate_case(case, i)

        question = case["question"].strip()
        results = search_documents(documents_dir, question, top_k)
        if case["answerable"]:
            answerable_total += 1
            if any(_matches_expected(result, case) for result in results):
                answerable_hits += 1
        else:
            not_answerable_total += 1
            if not results:
                empty_result_hits += 1

    recall_at_k = answerable_hits / answerable_total if answerable_total else 0.0
    empty_result_accuracy = (
        empty_result_hits / not_answerable_total if not_answerable_total else 0.0
    )
    return {
        "total": len(cases),
        "answerable_total": answerable_total,
        "answerable_hits": answerable_hits,
        "recall_at_k": recall_at_k,
        "not_answerable_total": not_answerable_total,
        "empty_result_hits": empty_result_hits,
        "empty_result_accuracy": empty_result_accuracy,
    }
