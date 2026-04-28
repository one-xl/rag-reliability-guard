"""无 LLM 证据回答接口测试。"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.answerer import draft_answer
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


def test_answer_refuses_when_no_results(tmp_path):
    body = draft_answer("unknown topic", tmp_path / "documents")
    assert body["generator"] == "extractive"
    assert "没有检索到足够信息" in body["answer"]
    assert body["citations"] == []


def test_answer_keyword_with_citations(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "notes.pdf",
        [(0, "RAG uses retrieval evidence"), (1, "other text")],
    )
    r = client.post("/api/answer", json={"question": "retrieval", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "keyword"
    assert body["generator"] == "extractive"
    assert "[1]" in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["document_id"] == doc_id
    assert body["citations"][0]["chunk_index"] == 0


def test_answer_bm25_method(client, tmp_path):
    doc_id = "00000000-0000-4000-8000-000000000077"
    chunks = [(0, "unique the"), (1, "the the the the the")]
    for i in range(2, 10):
        chunks.append((i, "the"))
    _write_metadata(tmp_path / "documents", doc_id, "bm25.pdf", chunks)
    r = client.post(
        "/api/answer",
        json={"question": "unique the", "method": "bm25", "top_k": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "bm25"
    assert body["citations"][0]["chunk_index"] == 0


def test_answer_rejects_invalid_method(client):
    r = client.post("/api/answer", json={"question": "x", "method": "vector"})
    assert r.status_code == 400
    assert "method" in r.json()["detail"]


def test_answer_rejects_invalid_generator(client):
    r = client.post("/api/answer", json={"question": "x", "generator": "other"})
    assert r.status_code == 400
    assert "generator" in r.json()["detail"]


def test_answer_attaches_reliability_metrics(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "reliable.pdf",
        [(0, "RAG uses retrieval evidence")],
    )
    r = client.post(
        "/api/answer",
        json={"question": "retrieval", "min_support_rate": 0.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reliable"] is True
    assert body["faithfulness"]["support_rate"] >= 0.5
    assert "reliability_warning" not in body


def test_answer_rejects_invalid_min_support_rate(client):
    r = client.post(
        "/api/answer",
        json={"question": "x", "min_support_rate": "high"},
    )
    assert r.status_code == 400
    assert "min_support_rate" in r.json()["detail"]


def test_answer_doubao_generator_uses_citations(client, tmp_path, monkeypatch):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "doubao.pdf",
        [(0, "RAG needs cited evidence")],
    )

    def fake_generate(question, citations):
        assert question == "evidence"
        assert citations[0]["document_id"] == doc_id
        return "豆包生成答案 [1]"

    monkeypatch.setattr("app.answerer.generate_doubao_answer", fake_generate)
    r = client.post(
        "/api/answer",
        json={"question": "evidence", "generator": "doubao"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["generator"] == "doubao"
    assert body["answer"] == "豆包生成答案 [1]"
    assert body["citations"][0]["document_id"] == doc_id


def test_answer_rejects_empty_question(client):
    r = client.post("/api/answer", json={"question": "   "})
    assert r.status_code == 400
    assert "question" in r.json()["detail"]
