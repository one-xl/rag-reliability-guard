"""Dense and hybrid retrieval tests."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dense_retrieval import search_documents_dense, search_documents_hybrid
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    documents = tmp_path / "documents"
    monkeypatch.setattr("app.main.DATA_DIR", uploads)
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


def test_dense_search_returns_semantic_matches(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "paper.pdf",
        [
            (0, "Retrieval-Augmented Generation uses external evidence to answer questions."),
            (1, "The weather in Tokyo is mild during spring."),
            (2, "Neural networks learn representations from data."),
        ],
    )
    results = search_documents_dense(docs, "How does RAG work?", top_k=3)
    assert len(results) == 3
    assert results[0]["document_id"] == doc_id
    assert isinstance(results[0]["score"], float)
    assert results[0]["score"] > 0
    chunk_indices = [r["chunk_index"] for r in results]
    assert 0 in chunk_indices


def test_dense_search_empty_corpus(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    results = search_documents_dense(docs, "anything", top_k=5)
    assert results == []


def test_dense_search_empty_query(tmp_path):
    docs = tmp_path / "documents"
    _write_metadata(docs, str(uuid.uuid4()), "a.pdf", [(0, "some text")])
    assert search_documents_dense(docs, "", top_k=5) == []
    assert search_documents_dense(docs, "   ", top_k=5) == []


def test_hybrid_search_combines_scores(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "notes.pdf",
        [
            (0, "Machine learning models require large datasets for training."),
            (1, "The quick brown fox jumps over the lazy dog."),
        ],
    )
    results = search_documents_hybrid(docs, "machine learning datasets", top_k=2)
    assert len(results) >= 1
    assert results[0]["document_id"] == doc_id
    assert "bm25_score" in results[0]
    assert "dense_score" in results[0]
    assert isinstance(results[0]["score"], float)


def test_api_search_method_dense(client, tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "test.pdf",
        [(0, "Deep learning for natural language processing"), (1, "Cooking recipes for pasta")],
    )
    r = client.get("/api/search", params={"q": "neural network NLP", "method": "dense", "top_k": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "dense"
    assert len(body["results"]) == 2
    assert body["results"][0]["chunk_index"] == 0


def test_api_search_method_hybrid(client, tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "test.pdf",
        [(0, "Information retrieval with vector embeddings"), (1, "Random noise text")],
    )
    r = client.get("/api/search", params={"q": "vector retrieval", "method": "hybrid", "top_k": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "hybrid"
    assert len(body["results"]) >= 1
    assert "bm25_score" in body["results"][0]
    assert "dense_score" in body["results"][0]


def test_api_search_method_invalid_includes_dense(client):
    r = client.get("/api/search", params={"q": "test", "method": "vector"})
    assert r.status_code == 400
    detail = str(r.json())
    assert "dense" in detail


def test_answer_with_dense_method(client, tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "rag.pdf",
        [(0, "RAG retrieves evidence before generating answers.")],
    )
    r = client.post(
        "/api/v1/answer",
        json={"question": "How does RAG work?", "method": "dense", "top_k": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "dense"
    assert len(body["citations"]) >= 1


def test_answer_with_hybrid_method(client, tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "rag.pdf",
        [(0, "RAG retrieves evidence before generating answers.")],
    )
    r = client.post(
        "/api/v1/answer",
        json={"question": "RAG evidence retrieval", "method": "hybrid", "top_k": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "hybrid"
    assert len(body["citations"]) >= 1


def test_dense_search_prefers_semantic_over_keyword(tmp_path):
    doc_id = str(uuid.uuid4())
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        doc_id,
        "synonyms.pdf",
        [
            (0, "Automobiles and cars are vehicles used for transportation."),
            (1, "The cat sat on the mat."),
        ],
    )
    results = search_documents_dense(docs, "vehicle transport", top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_index"] == 0
