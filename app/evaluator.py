"""Retrieval evaluation helpers for small local benchmark cases."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from app.answerer import draft_answer
from app.faithfulness import check_answer_faithfulness
from app.search import search_documents

_REFUSAL_MARKERS = ("知识库中没有检索到足够信息", "暂时无法回答")
ANSWER_EVAL_CSV_FIELDS = [
    "question",
    "answerable",
    "retrieved_citation_count",
    "reliable",
    "support_rate",
    "hallucination_rate",
    "hit",
    "refusal_correct",
]


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


def _refusal_correct_unanswerable(answer: str, citations: list[dict]) -> bool:
    """True when no evidence was retrieved or the answer clearly refuses."""
    if not citations:
        return any(marker in answer for marker in _REFUSAL_MARKERS)
    return False


def evaluate_answer_cases(
    cases: list[dict],
    documents_dir: Path,
    *,
    method: str = "keyword",
    generator: str = "extractive",
    top_k: int = 5,
    min_support_rate: float | None = None,
) -> dict:
    """
    Run draft_answer per case and return reliability-oriented metrics for experiments.

    Rows include faithfulness rates; ``hit`` applies when ``answerable`` and expected
    citation fields match retrieved citations; ``refusal_correct`` when not answerable.
    """
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    rows: list[dict] = []
    answerable_total = 0
    answerable_hits = 0
    unanswerable_total = 0
    refusal_correct_count = 0
    support_rates: list[float] = []
    hallucination_rates: list[float] = []

    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {i}: must be an object")
        _validate_case(case, i)

        question = case["question"].strip()
        draft = draft_answer(
            question,
            documents_dir,
            top_k=top_k,
            method=method,
            generator=generator,
            min_support_rate=min_support_rate,
        )
        citations = draft.get("citations") or []
        if not isinstance(citations, list):
            citations = []
        n_citations = len(citations)
        answer = draft.get("answer") or ""
        faithfulness = draft.get("faithfulness") or check_answer_faithfulness(
            str(answer), citations
        )
        sr = float(faithfulness["support_rate"])
        hr = float(faithfulness["hallucination_rate"])
        support_rates.append(sr)
        hallucination_rates.append(hr)

        reliable = draft.get("reliable")
        if min_support_rate is None:
            reliable = None

        answerable = bool(case["answerable"])
        hit: bool | None = None
        refusal_correct: bool | None = None

        if answerable:
            answerable_total += 1
            hit = any(
                isinstance(c, dict) and _matches_expected(c, case) for c in citations
            )
            if hit:
                answerable_hits += 1
        else:
            unanswerable_total += 1
            refusal_correct = _refusal_correct_unanswerable(str(answer), citations)
            if refusal_correct:
                refusal_correct_count += 1

        rows.append(
            {
                "question": question,
                "answerable": answerable,
                "retrieved_citation_count": n_citations,
                "reliable": reliable,
                "support_rate": sr,
                "hallucination_rate": hr,
                "hit": hit,
                "refusal_correct": refusal_correct,
            }
        )

    citation_hit_rate = answerable_hits / answerable_total if answerable_total else 0.0
    refusal_accuracy = (
        refusal_correct_count / unanswerable_total if unanswerable_total else 0.0
    )
    mean_support = sum(support_rates) / len(support_rates) if support_rates else 0.0
    mean_hallucination = (
        sum(hallucination_rates) / len(hallucination_rates) if hallucination_rates else 0.0
    )

    return {
        "method": method,
        "generator": generator,
        "top_k": top_k,
        "min_support_rate": min_support_rate,
        "rows": rows,
        "aggregate": {
            "total": len(cases),
            "answerable_total": answerable_total,
            "answerable_hits": answerable_hits,
            "citation_hit_rate": citation_hit_rate,
            "unanswerable_total": unanswerable_total,
            "refusal_correct_count": refusal_correct_count,
            "refusal_accuracy": refusal_accuracy,
            "mean_support_rate": mean_support,
            "mean_hallucination_rate": mean_hallucination,
        },
    }


def answer_evaluation_to_csv(evaluation: dict) -> str:
    """Serialize per-case answer evaluation rows to CSV text."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=ANSWER_EVAL_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in evaluation.get("rows", []):
        writer.writerow({field: row.get(field, "") for field in ANSWER_EVAL_CSV_FIELDS})
    return output.getvalue()


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
