"""检索评测模块与接口测试。"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.evaluator import evaluate_retrieval
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
