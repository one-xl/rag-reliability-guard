"""Extractive answer drafting from retrieved evidence chunks."""

from __future__ import annotations

import re
from pathlib import Path

from app.bm25 import search_documents_bm25
from app.faithfulness import check_answer_faithfulness
from app.llm_client import generate_doubao_answer
from app.search import iter_indexable_chunks, search_documents

VALID_METHODS = {"keyword", "bm25"}
VALID_GENERATORS = {"extractive", "doubao"}
REFUSAL_ANSWER = "知识库中没有检索到足够信息，暂时无法回答该问题。"

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "paper",
    "set",
    "step",
    "the",
    "this",
    "to",
    "uploaded",
    "what",
    "with",
}


def retrieve_for_method(documents_dir: Path, question: str, top_k: int, method: str) -> list[dict]:
    if method == "keyword":
        return search_documents(documents_dir, question, top_k)
    if method == "bm25":
        return search_documents_bm25(documents_dir, question, top_k)
    raise ValueError("method must be keyword or bm25")


def _content_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0).lower()
        if token.isascii() and (len(token) < 3 or token in _STOPWORDS):
            continue
        tokens.add(token)
    return tokens


def evidence_relevance_overlap(
    question: str,
    citations: list[dict],
    evidence_texts: list[str] | None = None,
) -> dict:
    """Return query-token coverage by citation previews for refusal gating."""
    query_tokens = _content_tokens(question)
    if not query_tokens:
        return {"query_terms": [], "matched_terms": [], "overlap_rate": 0.0}

    if evidence_texts is None:
        evidence_texts = [
            str(citation.get("text_preview", ""))
            for citation in citations
            if isinstance(citation, dict)
        ]
    evidence = " ".join(evidence_texts)
    evidence_tokens = _content_tokens(evidence)
    matched = sorted(query_tokens & evidence_tokens)
    return {
        "query_terms": sorted(query_tokens),
        "matched_terms": matched,
        "overlap_rate": len(matched) / len(query_tokens),
    }


def _load_evidence_texts(documents_dir: Path, citations: list[dict]) -> list[str]:
    needed = {
        (citation.get("document_id"), citation.get("chunk_index"))
        for citation in citations
        if isinstance(citation, dict)
    }
    if not needed:
        return []

    texts: dict[tuple[str, int], str] = {}
    for doc_id, _filename, chunk_index, text in iter_indexable_chunks(documents_dir):
        key = (doc_id, chunk_index)
        if key in needed:
            texts[key] = text

    return [
        texts.get((citation.get("document_id"), citation.get("chunk_index")), "")
        for citation in citations
        if isinstance(citation, dict)
    ]


def draft_answer(
    question: str,
    documents_dir: Path,
    top_k: int = 5,
    method: str = "keyword",
    generator: str = "extractive",
    min_support_rate: float | None = None,
    min_relevance_overlap: float | None = None,
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
        answer = generate_doubao_answer(stripped, citations)
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

    evidence_lines = [
        f"[{citation['index']}] {citation['text_preview']}" for citation in citations
    ]
    answer = "根据知识库中检索到的证据，可以参考以下内容：\n" + "\n".join(
        evidence_lines
    )
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
            response["answer"],
            response["citations"],
        )
        response["reliable"] = False
        response["reliability_warning"] = "未检索到证据，答案不可靠。"
    return response


def _attach_reliability(response: dict, min_support_rate: float | None) -> dict:
    if min_support_rate is None:
        return response

    faithfulness = check_answer_faithfulness(response["answer"], response["citations"])
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
