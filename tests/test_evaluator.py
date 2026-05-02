"""检索评测模块与接口测试。"""

import csv
import json
import uuid
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.evaluator import answer_evaluation_to_csv, evaluate_answer_cases, evaluate_retrieval
from app.llm_client import LLMRequestError
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    documents = tmp_path / "documents"
    monkeypatch.setattr("app.main.DOCUMENTS_DIR", documents)
    return TestClient(app)


def _write_metadata(path: Path, doc_id: str, filename: str, chunks: list[tuple[int, str]]) -> None:
    payload = {
        "id": doc_id,
        "original_filename": filename,
        "chunks": [
            {"index": idx, "text": text, "char_count": len(text)} for idx, text in chunks
        ],
    }
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{doc_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_evaluate_answerable_hit(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, "rag.pdf", [(0, "retrieval augmented generation")])
    metrics = evaluate_retrieval(
        [
            {
                "question": "retrieval",
                "answerable": True,
                "expected_document_id": doc_id,
                "expected_chunk_index": 0,
            }
        ],
        docs,
        top_k=5,
    )
    assert metrics["answerable_total"] == 1
    assert metrics["answerable_hits"] == 1
    assert metrics["recall_at_k"] == 1.0


def test_evaluate_answerable_miss(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, "rag.pdf", [(0, "retrieval augmented generation")])
    metrics = evaluate_retrieval(
        [
            {
                "question": "missing",
                "answerable": True,
                "expected_document_id": doc_id,
                "expected_chunk_index": 0,
            }
        ],
        docs,
        top_k=5,
    )
    assert metrics["answerable_hits"] == 0
    assert metrics["recall_at_k"] == 0.0


def test_evaluate_unanswerable_empty_result(tmp_path):
    metrics = evaluate_retrieval(
        [{"question": "unknown topic", "answerable": False}],
        tmp_path / "documents",
        top_k=5,
    )
    assert metrics["not_answerable_total"] == 1
    assert metrics["empty_result_hits"] == 1
    assert metrics["empty_result_accuracy"] == 1.0


def test_evaluate_rejects_invalid_cases(tmp_path):
    with pytest.raises(ValueError, match="cases must be a list"):
        evaluate_retrieval({"question": "x"}, tmp_path / "documents", top_k=5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="answerable"):
        evaluate_retrieval([{"question": "x"}], tmp_path / "documents", top_k=5)
    with pytest.raises(ValueError, match="expected"):
        evaluate_retrieval(
            [{"question": "x", "answerable": True}],
            tmp_path / "documents",
            top_k=5,
        )


def test_evaluate_endpoint(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "eval.pdf",
        [(0, "faithful citation retrieval")],
    )
    r = client.post(
        "/api/evaluate/retrieval",
        json={
            "top_k": 3,
            "cases": [
                {
                    "question": "citation",
                    "answerable": True,
                    "expected_document_id": doc_id,
                    "expected_chunk_index": 0,
                },
                {"question": "totally absent", "answerable": False},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["top_k"] == 3
    assert body["total"] == 2
    assert body["recall_at_k"] == 1.0
    assert body["empty_result_accuracy"] == 1.0


def test_evaluate_endpoint_rejects_bad_payload(client):
    r = client.post("/api/evaluate/retrieval", json={"cases": [{"question": "x"}]})
    assert r.status_code == 400
    assert "answerable" in r.json()["detail"]

    r2 = client.post("/api/evaluate/retrieval", json={"top_k": 0, "cases": []})
    assert r2.status_code == 422


def test_evaluate_answer_cases_answerable_hit(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, "rag.pdf", [(0, "retrieval augmented generation")])
    out = evaluate_answer_cases(
        [
            {
                "question": "retrieval",
                "answerable": True,
                "expected_document_id": doc_id,
                "expected_chunk_index": 0,
            }
        ],
        docs,
        method="keyword",
        generator="extractive",
        top_k=5,
    )
    row = out["rows"][0]
    assert row["answerable"] is True
    assert row["hit"] is True
    assert row["refusal_correct"] is None
    assert row["retrieved_citation_count"] >= 1
    agg = out["aggregate"]
    assert agg["answerable_total"] == 1
    assert agg["answerable_hits"] == 1
    assert agg["citation_hit_rate"] == 1.0


def test_evaluate_answer_cases_unanswerable_refusal(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir(parents=True)
    out = evaluate_answer_cases(
        [{"question": "zzz absent query xyz", "answerable": False}],
        docs,
        generator="extractive",
        top_k=5,
    )
    row = out["rows"][0]
    assert row["answerable"] is False
    assert row["hit"] is None
    assert row["refusal_correct"] is True
    assert row["retrieved_citation_count"] == 0
    agg = out["aggregate"]
    assert agg["refusal_correct_count"] == 1
    assert agg["refusal_accuracy"] == 1.0


def test_evaluate_answer_cases_unanswerable_refusal_by_relevance_gate(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "rag.pdf",
        [(0, "This paper discusses retrieval augmented generation evidence.")],
    )
    out = evaluate_answer_cases(
        [{"question": "paper quantum chip manufacturing recipe", "answerable": False}],
        docs,
        method="bm25",
        generator="extractive",
        top_k=3,
        min_support_rate=0.5,
        min_relevance_overlap=0.4,
    )
    row = out["rows"][0]
    assert row["refusal_correct"] is True
    assert row["retrieved_citation_count"] == 0
    assert row["reliable"] is False
    agg = out["aggregate"]
    assert agg["refusal_accuracy"] == 1.0
    assert out["min_relevance_overlap"] == 0.4


def test_evaluate_answer_cases_counts_refusal_even_with_citations(tmp_path, monkeypatch):
    def fake_draft_answer(*_args, **_kwargs):
        return {
            "answer": "I cannot answer because there is not enough information.",
            "citations": [{"document_id": "d", "chunk_index": 0, "text_preview": "context"}],
            "faithfulness": {
                "support_rate": 0.0,
                "hallucination_rate": 1.0,
                "unsupported_claim_rate": 1.0,
                "hallucination_proxy_rate": 1.0,
            },
        }

    monkeypatch.setattr("app.evaluator.draft_answer", fake_draft_answer)
    out = evaluate_answer_cases(
        [{"question": "private key?", "answerable": False}],
        tmp_path / "documents",
    )
    row = out["rows"][0]
    assert row["retrieved_citation_count"] == 1
    assert row["refusal_correct"] is True
    assert out["aggregate"]["refusal_accuracy"] == 1.0


def test_evaluate_answer_cases_continue_on_error_records_failed_row(tmp_path, monkeypatch):
    def fake_draft_answer(*_args, **_kwargs):
        raise LLMRequestError("upstream timeout")

    monkeypatch.setattr("app.evaluator.draft_answer", fake_draft_answer)
    out = evaluate_answer_cases(
        [
            {
                "question": "alpha",
                "answerable": True,
                "expected_document_id": "doc-1",
            }
        ],
        tmp_path / "documents",
        generator="doubao",
        min_support_rate=0.5,
        continue_on_error=True,
    )
    row = out["rows"][0]
    assert row["error"] == "upstream timeout"
    assert row["reliable"] is False
    assert row["hit"] is False
    assert out["continue_on_error"] is True
    assert out["aggregate"]["error_count"] == 1
    assert out["aggregate"]["answerable_total"] == 1


def test_evaluate_answer_cases_raises_without_continue_on_error(tmp_path, monkeypatch):
    def fake_draft_answer(*_args, **_kwargs):
        raise LLMRequestError("upstream timeout")

    monkeypatch.setattr("app.evaluator.draft_answer", fake_draft_answer)
    with pytest.raises(LLMRequestError):
        evaluate_answer_cases(
            [
                {
                    "question": "alpha",
                    "answerable": True,
                    "expected_document_id": "doc-1",
                }
            ],
            tmp_path / "documents",
            generator="doubao",
        )


def test_evaluate_answer_cases_aggregate_counts(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, "x.pdf", [(0, "alpha beta gamma delta")])
    out = evaluate_answer_cases(
        [
            {"question": "alpha beta", "answerable": True, "expected_document_id": doc_id},
            {"question": "qqqzzz unmatched noise", "answerable": False},
        ],
        docs,
        method="keyword",
        generator="extractive",
        top_k=5,
        min_support_rate=0.5,
    )
    agg = out["aggregate"]
    assert agg["total"] == 2
    assert agg["answerable_total"] == 1
    assert agg["unanswerable_total"] == 1
    assert agg["answerable_hits"] == 1
    assert agg["refusal_correct_count"] == 1
    assert "mean_support_rate" in agg and "mean_hallucination_rate" in agg
    assert 0.0 <= agg["mean_support_rate"] <= 1.0
    rows = out["rows"]
    assert rows[0]["reliable"] is not None
    assert isinstance(rows[0]["support_rate"], float)


def test_evaluate_answer_cases_rejects_invalid_cases(tmp_path):
    with pytest.raises(ValueError, match="cases must be a list"):
        evaluate_answer_cases("x", tmp_path / "documents")  # type: ignore[arg-type]


def test_evaluate_answers_endpoint_success(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "bench.pdf",
        [(0, "benchmark citation evidence text")],
    )
    r = client.post(
        "/api/evaluate/answers",
        json={
            "method": "keyword",
            "generator": "extractive",
            "top_k": 4,
            "cases": [
                {
                    "question": "benchmark citation",
                    "answerable": True,
                    "expected_document_id": doc_id,
                    "expected_chunk_index": 0,
                },
                {"question": "___no_hits_expected___", "answerable": False},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "keyword"
    assert body["generator"] == "extractive"
    assert body["top_k"] == 4
    assert len(body["rows"]) == 2
    assert body["aggregate"]["answerable_hits"] == 1


def test_evaluate_answers_endpoint_invalid_payload(client):
    r = client.post("/api/evaluate/answers", json={"cases": "not-a-list"})
    assert r.status_code == 422

    r2 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "top_k": 0, "generator": "extractive"},
    )
    assert r2.status_code == 422

    r3 = client.post(
        "/api/evaluate/answers",
        json={"cases": [{"question": "x"}], "generator": "extractive"},
    )
    assert r3.status_code == 400
    assert "answerable" in r3.json()["detail"]

    r4 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "method": "neither"},
    )
    assert r4.status_code == 422

    r5 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "generator": "unknown_gen"},
    )
    assert r5.status_code == 422

    r6 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "min_support_rate": "high"},
    )
    assert r6.status_code == 422

    r7 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "min_relevance_overlap": "high"},
    )
    assert r7.status_code == 422

    r8 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "min_support_rate": 1.5},
    )
    assert r8.status_code == 422

    r9 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "continue_on_error": "yes"},
    )
    assert r9.status_code == 422


def test_answer_evaluation_to_csv():
    csv_text = answer_evaluation_to_csv(
        {
            "rows": [
                {
                    "question": "q1",
                    "answerable": True,
                    "retrieved_citation_count": 2,
                    "reliable": True,
                    "support_rate": 0.8,
                    "hallucination_rate": 0.2,
                    "hit": True,
                    "refusal_correct": None,
                }
            ]
        }
    )
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert rows[0]["question"] == "q1"
    assert rows[0]["answerable"] == "True"
    assert rows[0]["retrieved_citation_count"] == "2"
    assert rows[0]["support_rate"] == "0.8"


def test_evaluate_answers_export_endpoint(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "export.pdf",
        [(0, "csv export evidence")],
    )
    r = client.post(
        "/api/evaluate/answers/export",
        json={
            "method": "keyword",
            "generator": "extractive",
            "top_k": 5,
            "min_support_rate": 0.5,
            "cases": [
                {
                    "question": "csv export",
                    "answerable": True,
                    "expected_document_id": doc_id,
                    "expected_chunk_index": 0,
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "answer_evaluation.csv" in r.headers["content-disposition"]
    rows = list(csv.DictReader(StringIO(r.text)))
    assert rows[0]["question"] == "csv export"
    assert rows[0]["answerable"] == "True"
    assert rows[0]["hit"] == "True"
    assert "support_rate" in rows[0]


def test_evaluate_answers_export_rejects_invalid_payload(client):
    r = client.post("/api/evaluate/answers/export", json={"cases": "bad"})
    assert r.status_code == 422
