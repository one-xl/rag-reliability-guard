"""关键词检索接口与 search_documents 行为测试。"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bm25 import search_documents_bm25, tokenize
from app.document_index import get_document_index
from app.main import app
from app.search import search_documents


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


def test_search_rejects_empty_query(client):
    r0 = client.get("/api/search", params={"q": ""})
    assert r0.status_code == 400
    r1 = client.get("/api/search", params={"q": "  \t "})
    assert r1.status_code == 400
    r2 = client.get("/api/search")
    assert r2.status_code == 400


def test_search_no_documents_empty_results(client):
    r = client.get("/api/search", params={"q": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "anything"
    assert body["top_k"] == 5
    assert body["method"] == "keyword"
    assert body["results"] == []


def test_search_successful_match(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "notes.pdf",
        [(0, "Intro"), (1, "Hello World from chunk"), (2, "Outro")],
    )
    r = client.get("/api/search", params={"q": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["top_k"] == 5
    assert body["method"] == "keyword"
    assert len(body["results"]) == 1
    hit = body["results"][0]
    assert hit["document_id"] == doc_id
    assert hit["original_filename"] == "notes.pdf"
    assert hit["chunk_index"] == 1
    assert hit["score"] == 1
    assert hit["text_preview"].startswith("Hello World")


def test_search_ranking_by_score(tmp_path):
    low_id = "00000000-0000-4000-8000-000000000001"
    high_id = "00000000-0000-4000-8000-000000000002"
    docs = tmp_path / "documents"
    _write_metadata(
        docs,
        low_id,
        "a.pdf",
        [(0, "alpha only once"), (1, "beta")],
    )
    _write_metadata(
        docs,
        high_id,
        "b.pdf",
        [(0, "alpha alpha alpha"), (1, "gamma")],
    )
    rows = search_documents(docs, "alpha", top_k=10)
    assert [r["chunk_index"] for r in rows[:2]] == [0, 0]
    assert rows[0]["document_id"] == high_id
    assert rows[0]["score"] == 3
    assert rows[1]["document_id"] == low_id
    assert rows[1]["score"] == 1


def test_search_top_k_limits_results(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "c.pdf",
        [
            (0, "kw here"),
            (1, "kw there"),
            (2, "kw everywhere"),
        ],
    )
    r = client.get("/api/search", params={"q": "kw", "top_k": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["top_k"] == 2
    assert body["method"] == "keyword"
    assert len(body["results"]) == 2


def test_search_top_k_validation(client):
    r = client.get("/api/search", params={"q": "x", "top_k": 0})
    assert r.status_code == 422
    r2 = client.get("/api/search", params={"q": "x", "top_k": 21})
    assert r2.status_code == 422


def test_api_search_method_invalid(client):
    r = client.get("/api/search", params={"q": "test", "method": "vector"})
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "keyword" in str(detail) and "bm25" in str(detail).lower()


def test_default_keyword_same_as_explicit_keyword(client, tmp_path):
    doc_id = str(uuid.uuid4())
    _write_metadata(
        tmp_path / "documents",
        doc_id,
        "n.pdf",
        [(0, "only match termxy here")],
    )
    r1 = client.get("/api/search", params={"q": "termxy"})
    r2 = client.get("/api/search", params={"q": "termxy", "method": "keyword"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert r1.json()["method"] == "keyword"


def test_bm25_ranking_idf_dominates_rare_term(tmp_path):
    """
    关键词对常见词 the 的重复命中计分高；BM25 对仅出现在一处的 rare word 更敏感。
    """
    doc_id = "00000000-0000-4000-8000-000000000055"
    docs = tmp_path / "documents"
    chunks = [(0, "unique the"), (1, "the the the the the")]
    for i in range(2, 10):
        chunks.append((i, "the"))
    _write_metadata(docs, doc_id, "corpus.pdf", chunks)
    kw = search_documents(docs, "unique the", top_k=2)
    bm = search_documents_bm25(docs, "unique the", top_k=2)
    assert kw[0]["chunk_index"] == 1
    assert kw[0]["score"] > kw[1]["score"]
    assert bm[0]["chunk_index"] == 0
    assert bm[0]["score"] > bm[1]["score"]


def test_tokenize_english_and_cjk():
    assert tokenize("Hello 世界!") == ["hello", "世界"]
    assert tokenize("alpha-beta") == ["alpha", "beta"]


def test_api_search_method_bm25(client, tmp_path):
    doc_id = "00000000-0000-4000-8000-000000000066"
    docs = tmp_path / "documents"
    chunks = [(0, "unique the"), (1, "the the the the the")]
    for i in range(2, 10):
        chunks.append((i, "the"))
    _write_metadata(docs, doc_id, "corpus.pdf", chunks)
    r_kw = client.get("/api/search", params={"q": "unique the", "method": "keyword"})
    r_bm = client.get("/api/search", params={"q": "unique the", "method": "bm25"})
    assert r_kw.json()["method"] == "keyword"
    assert r_bm.json()["method"] == "bm25"
    assert r_kw.json()["results"][0]["chunk_index"] == 1
    assert r_bm.json()["results"][0]["chunk_index"] == 0
    assert isinstance(r_bm.json()["results"][0]["score"], float)


def test_document_index_refreshes_when_metadata_changes(tmp_path):
    doc_id = "00000000-0000-4000-8000-000000000088"
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, "cache.pdf", [(0, "alpha evidence")])
    first = get_document_index(docs)
    assert first.text_by_key[(doc_id, 0)] == "alpha evidence"

    _write_metadata(docs, doc_id, "cache.pdf", [(0, "alpha evidence plus beta")])
    second = get_document_index(docs)
    assert second.text_by_key[(doc_id, 0)] == "alpha evidence plus beta"
    assert second is not first
