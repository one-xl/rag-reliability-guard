"""检索评测模块与接口测试。"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.evaluator import evaluate_answer_cases, evaluate_retrieval
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
    assert r2.status_code == 400


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
    assert r.status_code == 400
    assert "cases" in r.json()["detail"]

    r2 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "top_k": 0, "generator": "extractive"},
    )
    assert r2.status_code == 400

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
    assert r4.status_code == 400

    r5 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "generator": "unknown_gen"},
    )
    assert r5.status_code == 400

    r6 = client.post(
        "/api/evaluate/answers",
        json={"cases": [], "min_support_rate": "high"},
    )
    assert r6.status_code == 400
