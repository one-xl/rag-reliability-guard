"""上传与健康检查接口的最小回归测试。"""

import json
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app
from app.text_chunker import chunk_text


@pytest.fixture
def client(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    documents = tmp_path / "documents"
    monkeypatch.setattr("app.main.DATA_DIR", uploads)
    monkeypatch.setattr("app.main.DOCUMENTS_DIR", documents)
    return TestClient(app)


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_upload_valid_pdf(client):
    pdf = _minimal_pdf_bytes()
    r = client.post(
        "/api/documents/upload",
        files={"file": ("hello.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["page_count"] == 1
    assert "id" in body and "saved_as" in body
    assert body["original_filename"] == "hello.pdf"


def test_upload_rejects_non_pdf_extension(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_rejects_empty_file(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 2048)
    blob = b"x" * 3000
    r = client.post(
        "/api/documents/upload",
        files={"file": ("big.pdf", blob, "application/pdf")},
    )
    assert r.status_code == 413


def test_upload_invalid_pdf_bytes_no_leak(client):
    """扩展名为 .pdf 但内容非法时应 422，且响应中不含底层库名或栈信息。"""
    r = client.post(
        "/api/documents/upload",
        files={"file": ("bad.pdf", b"not pdf content", "application/pdf")},
    )
    assert r.status_code == 422
    detail = r.json().get("detail", "")
    assert detail == "无法解析该 PDF，请确认文件未损坏且为有效 PDF"
    assert "pypdf" not in detail.lower()
    assert "PdfReader" not in detail


def test_upload_creates_metadata_json(client, tmp_path):
    pdf = _minimal_pdf_bytes()
    r = client.post(
        "/api/documents/upload",
        files={"file": ("meta.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 200
    doc_id = r.json()["id"]
    meta_path = tmp_path / "documents" / f"{doc_id}.json"
    assert meta_path.is_file()
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    assert raw["id"] == doc_id
    assert raw["original_filename"] == "meta.pdf"
    assert "saved_as" in raw and raw["saved_as"].endswith(".pdf")
    assert raw["page_count"] == 1
    assert raw["char_count"] >= 0
    assert "text_preview" in raw
    assert "chunks" in raw
    for i, ch in enumerate(raw["chunks"]):
        assert ch["index"] == i
        assert "text" in ch and "char_count" in ch
        assert ch["char_count"] == len(ch["text"])


def test_list_documents_after_upload(client):
    r0 = client.post(
        "/api/documents/upload",
        files={"file": ("a.pdf", _minimal_pdf_bytes(), "application/pdf")},
    )
    r1 = client.post(
        "/api/documents/upload",
        files={"file": ("b.pdf", _minimal_pdf_bytes(), "application/pdf")},
    )
    id_a, id_b = r0.json()["id"], r1.json()["id"]
    r = client.get("/api/documents")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    by_id = {x["id"]: x for x in items}
    assert id_a in by_id and id_b in by_id
    for item in items:
        assert "chunks" not in item
        assert "chunk_count" in item


def test_get_document_detail(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("d.pdf", _minimal_pdf_bytes(), "application/pdf")},
    )
    doc_id = r.json()["id"]
    r2 = client.get(f"/api/documents/{doc_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == doc_id
    assert "chunks" in body and isinstance(body["chunks"], list)


def test_get_document_missing_404(client):
    missing = str(uuid.uuid4())
    r = client.get(f"/api/documents/{missing}")
    assert r.status_code == 404


def test_chunk_count_consistent_with_chunks(client, monkeypatch):
    from app import main

    known = "x" * 2500
    monkeypatch.setattr("app.main.extract_text_from_pdf", lambda _b: (known, 1))
    r = client.post(
        "/api/documents/upload",
        files={"file": ("k.pdf", b"fake", "application/pdf")},
    )
    assert r.status_code == 200
    doc_id = r.json()["id"]
    meta_path = main.DOCUMENTS_DIR / f"{doc_id}.json"
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = chunk_text(known, chunk_size=main.CHUNK_SIZE, overlap=main.CHUNK_OVERLAP)
    assert raw["chunk_count"] == len(expected) == len(raw["chunks"])
