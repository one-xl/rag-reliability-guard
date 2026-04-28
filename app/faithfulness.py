"""Lightweight evidence support checks for generated answers."""

from __future__ import annotations

import re


_ASCII_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "it",
    "this",
    "that",
    "是",
    "的",
    "了",
    "和",
    "与",
    "及",
    "在",
    "中",
    "为",
    "对",
    "由",
    "可以",
    "一个",
}


def split_claims(answer: str) -> list[str]:
    """Split an answer into short factual-looking claims."""
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(answer) if part.strip()]


def extract_keywords(text: str) -> set[str]:
    """Extract conservative English words and Han characters for support matching."""
    keywords: set[str] = set()
    for token in _ASCII_TOKEN_RE.findall(text.lower()):
        if len(token) >= 2 and token not in _STOPWORDS:
            keywords.add(token)
    for token in _CJK_RE.findall(text):
        if token not in _STOPWORDS:
            keywords.add(token)
    return keywords


def _evidence_text(citations: list[dict]) -> str:
    return "\n".join(
        str(item.get("text_preview", "")) for item in citations if isinstance(item, dict)
    )


def check_answer_faithfulness(answer: str, citations: list[dict]) -> dict:
    """
    Estimate whether answer claims are supported by cited evidence.

    This is a deterministic proxy metric, not a semantic entailment model. A claim is
    supported when at least half of its extracted keywords appear in citation previews.
    """
    claims = split_claims(answer)
    evidence_keywords = extract_keywords(_evidence_text(citations))
    results: list[dict] = []

    for claim in claims:
        claim_keywords = extract_keywords(claim)
        if not claim_keywords:
            supported = bool(citations)
            overlap: list[str] = []
        else:
            overlap_set = claim_keywords & evidence_keywords
            supported = len(overlap_set) / len(claim_keywords) >= 0.5
            overlap = sorted(overlap_set)
        results.append(
            {
                "claim": claim,
                "supported": supported,
                "keywords": sorted(claim_keywords),
                "matched_keywords": overlap,
            }
        )

    supported_count = sum(1 for item in results if item["supported"])
    total = len(results)
    support_rate = supported_count / total if total else 0.0
    return {
        "claim_count": total,
        "supported_claim_count": supported_count,
        "support_rate": support_rate,
        "hallucination_rate": 1.0 - support_rate if total else 0.0,
        "claims": results,
    }
