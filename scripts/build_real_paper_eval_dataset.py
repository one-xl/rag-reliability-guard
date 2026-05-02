"""Build a local answer-evaluation dataset from the currently indexed real papers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = Path("datasets/real_paper_answer_eval_cases.json")

ANSWERABLE_QUERIES = [
    "Self-RAG retrieve generate critique",
    "Self-RAG reflection tokens retrieve relevant critique",
    "retrieval augmented generation factuality self reflection",
    "adaptive retrieval in Self-RAG",
    "Self-RAG training critic model",
    "factuality evaluation reeval hallucination",
    "ReEval factuality evaluation benchmark",
    "hallucination evaluation natural language generation",
    "claim verification factual consistency evaluation",
    "large language model factuality evaluation",
    "retrieval evidence answer citation reliability",
    "faithfulness evaluation generated answers",
]

UNANSWERABLE_QUERIES = [
    "Does this paper give a step-by-step recipe for manufacturing a quantum chip?",
    "What is the latest stock price of NVIDIA today?",
    "How should I configure a Kubernetes cluster for this repository?",
    "Which restaurant near my home is best for dinner tonight?",
    "What are the private API keys used by the authors?",
    "How can I synthesize a new antibiotic from household materials?",
    "What is the weather forecast for Beijing next week?",
    "Which GPU should I buy during the next shopping festival?",
]


def _search_top_hit(base_url: str, query: str, *, method: str, top_k: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/search"
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url, params={"q": query, "method": method, "top_k": top_k})
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(f"search failed for {query!r}: {response.status_code} {response.text}") from exc
    body = response.json()
    results = body.get("results")
    if not isinstance(results, list) or not results:
        raise SystemExit(f"no search result for answerable query: {query}")
    hit = results[0]
    if not isinstance(hit.get("document_id"), str) or not isinstance(hit.get("chunk_index"), int):
        raise SystemExit(f"search result missing expected fields for query: {query}")
    return hit


def build_dataset(base_url: str, *, method: str, top_k: int) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for query in ANSWERABLE_QUERIES:
        hit = _search_top_hit(base_url, query, method=method, top_k=top_k)
        cases.append(
            {
                "question": query,
                "answerable": True,
                "expected_document_id": hit["document_id"],
                "expected_chunk_index": hit["chunk_index"],
            }
        )

    cases.extend({"question": query, "answerable": False} for query in UNANSWERABLE_QUERIES)
    return {
        "_comment": "Generated from currently indexed real AI papers. Rebuild after re-uploading documents because document IDs can change.",
        "top_k": top_k,
        "method": method,
        "generator": "extractive",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a real-paper answer evaluation dataset from local search results."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--method", default="bm25", choices=["keyword", "bm25"])
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    dataset = build_dataset(args.base_url, method=args.method, top_k=args.top_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"cases {len(dataset['cases'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
