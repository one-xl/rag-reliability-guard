"""Extractive answer drafting from retrieved evidence chunks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from app.bm25 import search_documents_bm25
from app.dense_retrieval import search_documents_dense, search_documents_hybrid
from app.document_index import get_document_index
from app.faithfulness import check_answer_faithfulness, extract_keywords
from app.llm_client import LLMConfigurationError, LLMRequestError, generate_doubao_answer
from app.search import search_documents

VALID_METHODS = {"keyword", "bm25", "dense", "hybrid"}
VALID_GENERATORS = {"extractive", "doubao"}
REFUSAL_ANSWER = "知识库中没有检索到足够信息，暂时无法回答该问题。"


def retrieve_for_method(documents_dir: Path, question: str, top_k: int, method: str) -> list[dict]:
    if method == "keyword":
        return search_documents(documents_dir, question, top_k)
    if method == "bm25":
        return search_documents_bm25(documents_dir, question, top_k)
    if method == "dense":
        return search_documents_dense(documents_dir, question, top_k)
    if method == "hybrid":
        return search_documents_hybrid(documents_dir, question, top_k)
    raise ValueError("method must be keyword, bm25, dense, or hybrid")


def evidence_relevance_overlap(
    question: str,
    citations: list[dict],
    evidence_texts: list[str] | None = None,
) -> dict:
    """Return query-token coverage by citation previews for refusal gating."""
    query_tokens = extract_keywords(question)
    if not query_tokens:
        return {"query_terms": [], "matched_terms": [], "overlap_rate": 0.0}

    if evidence_texts is None:
        evidence_texts = [
            str(citation.get("text_preview", ""))
            for citation in citations
            if isinstance(citation, dict)
        ]
    evidence = " ".join(evidence_texts)
    evidence_tokens = extract_keywords(evidence)
    matched = sorted(query_tokens & evidence_tokens)
    return {
        "query_terms": sorted(query_tokens),
        "matched_terms": matched,
        "overlap_rate": len(matched) / len(query_tokens),
    }


def _load_evidence_texts(documents_dir: Path, citations: list[dict]) -> list[str]:
    index = get_document_index(documents_dir)
    evidence_texts: list[str] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        document_id = citation.get("document_id")
        chunk_index = citation.get("chunk_index")
        if isinstance(document_id, str) and isinstance(chunk_index, int):
            evidence_texts.append(index.text_by_key.get((document_id, chunk_index), ""))
    return evidence_texts


def draft_answer(
    question: str,
    documents_dir: Path,
    top_k: int = 5,
    method: str = "keyword",
    generator: str = "extractive",
    min_support_rate: float | None = None,
    min_relevance_overlap: float | None = None,
    fallback_to_extractive: bool = True,
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
    if min_support_rate is not None and not 0.0 <= min_support_rate <= 1.0:
        raise ValueError("min_support_rate must be between 0 and 1")
    if min_relevance_overlap is not None and not 0.0 <= min_relevance_overlap <= 1.0:
        raise ValueError("min_relevance_overlap must be between 0 and 1")

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
        return _refusal_response(stripped, method, generator, top_k, min_support_rate)

    evidence_texts = _load_evidence_texts(documents_dir, citations)
    relevance = evidence_relevance_overlap(stripped, citations, evidence_texts)
    if (
        min_relevance_overlap is not None
        and relevance["overlap_rate"] < min_relevance_overlap
    ):
        response = _refusal_response(stripped, method, generator, top_k, min_support_rate)
        response["relevance"] = relevance
        response["reliable"] = False
        response["reliability_warning"] = (
            f"检索证据相关性覆盖率 {relevance['overlap_rate']:.2f} "
            f"低于阈值 {min_relevance_overlap:.2f}，已拒答。"
        )
        return response

    if generator == "doubao":
        try:
            answer = generate_doubao_answer(stripped, citations)
        except (LLMConfigurationError, LLMRequestError) as exc:
            if not fallback_to_extractive:
                raise
            response = _extractive_response(
                stripped,
                method,
                generator,
                top_k,
                citations,
                relevance,
            )
            response["fallback_generator"] = "extractive"
            response["llm_error"] = str(exc)
            return _attach_reliability(response, min_support_rate)
        response = {
            "question": stripped,
            "method": method,
            "generator": generator,
            "top_k": top_k,
            "answer": answer,
            "citations": citations,
            "relevance": relevance,
        }
        return _attach_reliability(response, min_support_rate)

    response = _extractive_response(stripped, method, generator, top_k, citations, relevance)
    return _attach_reliability(response, min_support_rate)


def _extractive_response(
    question: str,
    method: str,
    generator: str,
    top_k: int,
    citations: list[dict],
    relevance: dict,
) -> dict:
    evidence_lines = [
        f"[{citation['index']}] {citation['text_preview']}" for citation in citations
    ]
    answer = "根据知识库中检索到的证据，可以参考以下内容：\n" + "\n".join(
        evidence_lines
    )
    return {
        "question": question,
        "method": method,
        "generator": generator,
        "top_k": top_k,
        "answer": answer,
        "citations": citations,
        "relevance": relevance,
    }


def _refusal_response(
    question: str,
    method: str,
    generator: str,
    top_k: int,
    min_support_rate: float | None,
) -> dict:
    response = {
        "question": question,
        "method": method,
        "generator": generator,
        "top_k": top_k,
        "answer": REFUSAL_ANSWER,
        "citations": [],
    }
    if min_support_rate is not None:
        response["faithfulness"] = check_answer_faithfulness(
            cast(str, response["answer"]),
            cast(list[dict[Any, Any]], response["citations"]),
        )
        response["reliable"] = False
        response["reliability_warning"] = "未检索到证据，答案不可靠。"
    return response


def _attach_reliability(response: dict, min_support_rate: float | None) -> dict:
    if min_support_rate is None:
        return response

    faithfulness = check_answer_faithfulness(
        cast(str, response["answer"]),
        cast(list[dict[Any, Any]], response["citations"]),
    )
    support_rate = faithfulness["support_rate"]
    reliable = support_rate >= min_support_rate
    response["faithfulness"] = faithfulness
    response["reliable"] = reliable
    if not reliable:
        response["reliability_warning"] = (
            f"答案证据支持率 {support_rate:.2f} 低于阈值 {min_support_rate:.2f}，"
            "请谨慎使用或补充知识库证据。"
        )
    return response
