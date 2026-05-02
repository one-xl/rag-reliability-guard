"""上传与健康检查接口的最小回归测试。"""

import json
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.evaluator import answer_evaluation_to_csv
from app.main import app
from app.text_chunker import chunk_text

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def test_api_v1_and_legacy_aliases_are_available(client):
    legacy = client.get("/api/documents")
    versioned = client.get("/api/v1/documents")
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert legacy.json() == versioned.json() == []


def test_openapi_prefers_v1_paths(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/search" in paths
    assert "/api/search" not in paths


def test_api_v1_post_endpoint_works(client):
    r = client.post(
        "/api/v1/evaluate/faithfulness",
        json={
            "answer": "RAG retrieves evidence before answering.",
            "citations": [{"text": "RAG retrieves evidence before answering."}],
        },
    )
    assert r.status_code == 200
    assert "support_rate" in r.json()


def test_demo_external_eval_returns_cases_and_min_support_rate(client):
    r = client.get("/api/demo/external-eval")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("min_support_rate"), (int, float))
    cases = body.get("cases")
    assert isinstance(cases, list)
    assert len(cases) >= 6


def test_demo_external_eval_missing_file_returns_404_no_leak(client, monkeypatch, tmp_path):
    missing = tmp_path / "nope.json"
    monkeypatch.setattr("app.main.DEMO_EXTERNAL_EVAL_PATH", missing)
    r = client.get("/api/demo/external-eval")
    assert r.status_code == 404
    assert r.json().get("detail") == "内置评测 Demo 数据不可用"
    assert "Traceback" not in r.text


def test_demo_external_eval_corrupt_json_returns_503_no_leak(client, monkeypatch, tmp_path):
    bad = tmp_path / "demo_external_eval_cases.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr("app.main.DEMO_EXTERNAL_EVAL_PATH", bad)
    r = client.get("/api/demo/external-eval")
    assert r.status_code == 503
    assert r.json().get("detail") == "内置评测 Demo 数据不可用"
    assert "JSONDecodeError" not in r.text


def test_dashboard_includes_answer_eval_csv_download(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    js = client.get("/static/dashboard.js").text
    assert 'id="download-answer-eval-csv"' in html
    assert 'apiPath("/evaluate/answers/export")' in js
    assert 'const API_BASE = "/api/v1"' in js


def test_dashboard_includes_experiment_history_controls(client):
    """首页需包含：答案评测 save 勾选、刷新实验列表、实验详情加载（列表 + fetch 详情）。"""
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    js = client.get("/static/dashboard.js").text
    assert 'id="answer-eval-save"' in html
    assert "save=true" in html
    assert 'id="refresh-experiments"' in html
    assert 'id="experiments-list"' in html
    assert 'id="experiments-prev"' in html
    assert 'id="experiments-next"' in html
    assert 'id="experiment-detail-output"' in html
    assert "EXPERIMENT_PAGE_SIZE" in js
    assert "include_total=true" in js
    assert "apiPath(`/experiments/${encodeURIComponent(runId)}`)" in js


def test_dashboard_includes_document_delete_and_model_metadata_warning(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    js = client.get("/static/dashboard.js").text
    assert "delete-document" in js
    assert "DELETE" in js
    assert "window.confirm" in js
    assert "Demo 数据不代表真实模型排名" in html


def test_sample_answer_eval_cases_json_readable():
    path = REPO_ROOT / "datasets" / "sample_answer_eval_cases.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw["cases"]
    assert isinstance(cases, list)
    assert len(cases) >= 2
    answerable = [c for c in cases if c.get("answerable") is True]
    unanswerable = [c for c in cases if c.get("answerable") is False]
    assert answerable and unanswerable
    for c in answerable:
        assert "expected_document_id" in c or "expected_chunk_index" in c


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
    assert body["duplicate"] is False


def test_upload_duplicate_pdf_reuses_existing_document(client, tmp_path):
    pdf = _minimal_pdf_bytes()
    r0 = client.post(
        "/api/documents/upload",
        files={"file": ("first.pdf", pdf, "application/pdf")},
    )
    r1 = client.post(
        "/api/documents/upload",
        files={"file": ("second.pdf", pdf, "application/pdf")},
    )
    assert r0.status_code == 200
    assert r1.status_code == 200
    first = r0.json()
    second = r1.json()
    assert second["duplicate"] is True
    assert second["id"] == first["id"]
    assert len(list((tmp_path / "documents").glob("*.json"))) == 1


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
    pdf_a = _minimal_pdf_bytes()
    pdf_b = _minimal_pdf_bytes() + b"\n% distinct test fixture"
    r0 = client.post(
        "/api/documents/upload",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
    )
    r1 = client.post(
        "/api/documents/upload",
        files={"file": ("b.pdf", pdf_b, "application/pdf")},
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


def test_delete_document_removes_metadata_and_upload(client, tmp_path):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("delete-me.pdf", _minimal_pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    doc_id = r.json()["id"]
    meta_path = tmp_path / "documents" / f"{doc_id}.json"
    saved_as = r.json()["saved_as"]
    upload_path = tmp_path / "uploads" / saved_as
    assert meta_path.is_file()
    assert upload_path.is_file()

    r2 = client.delete(f"/api/documents/{doc_id}")
    assert r2.status_code == 200
    assert r2.json() == {"deleted": True, "id": doc_id}
    assert not meta_path.exists()
    assert not upload_path.exists()
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_delete_document_missing_404(client):
    missing = str(uuid.uuid4())
    r = client.delete(f"/api/documents/{missing}")
    assert r.status_code == 404


def test_chunk_count_consistent_with_chunks(client, monkeypatch):
    from app import main

    known = "x" * 2500
    monkeypatch.setattr("app.main.extract_text_from_pdf_stream", lambda _s: (known, 1))
    r = client.post(
        "/api/documents/upload",
        files={"file": ("k.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert r.status_code == 200
    doc_id = r.json()["id"]
    meta_path = main.DOCUMENTS_DIR / f"{doc_id}.json"
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = chunk_text(known, chunk_size=main.CHUNK_SIZE, overlap=main.CHUNK_OVERLAP)
    assert raw["chunk_count"] == len(expected) == len(raw["chunks"])


def _fake_answer_evaluation() -> dict:
    return {
        "method": "keyword",
        "generator": "extractive",
        "top_k": 5,
        "min_support_rate": None,
        "rows": [
            {
                "question": "q1",
                "answerable": True,
                "retrieved_citation_count": 0,
                "reliable": None,
                "support_rate": 1.0,
                "hallucination_rate": 0.0,
                "hit": True,
                "refusal_correct": None,
            }
        ],
        "aggregate": {
            "total": 1,
            "answerable_total": 1,
            "answerable_hits": 1,
            "citation_hit_rate": 1.0,
            "unanswerable_total": 0,
            "refusal_correct_count": 0,
            "refusal_accuracy": 0.0,
            "mean_support_rate": 1.0,
            "mean_hallucination_rate": 0.0,
        },
    }


def test_evaluate_answers_save_true_writes_json_and_csv(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    monkeypatch.setattr(
        "app.main.evaluate_answer_cases",
        lambda *args, **kwargs: _fake_answer_evaluation(),
    )
    r = client.post(
        "/api/evaluate/answers",
        json={
            "cases": [{"question": "x", "answerable": True, "expected_document_id": "d"}],
            "save": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    run_id = body["run_id"]
    assert uuid.UUID(run_id)
    assert "saved_paths" in body
    assert body["saved_paths"]["json"] == f"data/experiments/{run_id}.json"
    assert body["saved_paths"]["csv"] == f"data/experiments/{run_id}.csv"
    assert body["aggregate"]["total"] == 1

    jpath = experiments / f"{run_id}.json"
    cpath = experiments / f"{run_id}.csv"
    assert jpath.is_file()
    assert cpath.is_file()
    saved = json.loads(jpath.read_text(encoding="utf-8"))
    assert saved["run_id"] == run_id
    assert "created_at" in saved
    assert saved["method"] == "keyword"
    assert saved["aggregate"]["mean_support_rate"] == 1.0
    assert cpath.read_text(encoding="utf-8") == answer_evaluation_to_csv(_fake_answer_evaluation())


def test_evaluate_answers_without_save_has_no_run_metadata(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    monkeypatch.setattr(
        "app.main.evaluate_answer_cases",
        lambda *args, **kwargs: _fake_answer_evaluation(),
    )
    r = client.post(
        "/api/evaluate/answers",
        json={
            "cases": [{"question": "x", "answerable": True, "expected_document_id": "d"}],
            "save": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "run_id" not in body
    assert "saved_paths" not in body
    assert not experiments.exists()


def test_list_experiments_returns_summaries_newest_first(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    rid_a = str(uuid.uuid4())
    rid_b = str(uuid.uuid4())
    base = _fake_answer_evaluation()
    rec_a = {"run_id": rid_a, "created_at": "2026-01-01T00:00:00Z", **base}
    rec_b = {"run_id": rid_b, "created_at": "2026-02-01T00:00:00Z", **base}
    (experiments / f"{rid_a}.json").write_text(
        json.dumps(rec_a, ensure_ascii=False),
        encoding="utf-8",
    )
    (experiments / f"{rid_b}.json").write_text(
        json.dumps(rec_b, ensure_ascii=False),
        encoding="utf-8",
    )
    r = client.get("/api/experiments")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert items[0]["run_id"] == rid_b
    assert items[1]["run_id"] == rid_a
    for item in items:
        assert set(item.keys()) == {
            "run_id",
            "created_at",
            "method",
            "generator",
            "top_k",
            "total",
            "mean_support_rate",
            "mean_hallucination_rate",
        }
        assert item["method"] == "keyword"
        assert item["generator"] == "extractive"
        assert item["top_k"] == 5
        assert item["total"] == 1
        assert item["mean_support_rate"] == 1.0
        assert item["mean_hallucination_rate"] == 0.0


def test_list_experiments_supports_pagination(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    base = _fake_answer_evaluation()
    run_ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, run_id in enumerate(run_ids):
        record = {
            "run_id": run_id,
            "created_at": f"2026-01-0{i + 1}T00:00:00Z",
            **base,
        }
        (experiments / f"{run_id}.json").write_text(
            json.dumps(record, ensure_ascii=False),
            encoding="utf-8",
        )

    r = client.get("/api/experiments", params={"limit": 1, "offset": 1})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["run_id"] == run_ids[1]


def test_list_experiments_can_include_total_for_dashboard(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    base = _fake_answer_evaluation()
    run_ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, run_id in enumerate(run_ids):
        record = {
            "run_id": run_id,
            "created_at": f"2026-01-0{i + 1}T00:00:00Z",
            **base,
        }
        (experiments / f"{run_id}.json").write_text(
            json.dumps(record, ensure_ascii=False),
            encoding="utf-8",
        )

    r = client.get("/api/v1/experiments", params={"limit": 2, "offset": 1, "include_total": True})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [item["run_id"] for item in body["items"]] == [run_ids[1], run_ids[0]]


def test_get_experiment_returns_saved_json(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    run_id = str(uuid.uuid4())
    record = {"run_id": run_id, "created_at": "2026-03-01T00:00:00Z", **_fake_answer_evaluation()}
    (experiments / f"{run_id}.json").write_text(
        json.dumps(record, ensure_ascii=False),
        encoding="utf-8",
    )
    r = client.get(f"/api/experiments/{run_id}")
    assert r.status_code == 200
    assert r.json() == record


def test_get_experiment_missing_returns_404(client, monkeypatch, tmp_path):
    experiments = tmp_path / "experiments"
    experiments.mkdir(parents=True)
    monkeypatch.setattr("app.main.EXPERIMENTS_DIR", experiments)
    missing = str(uuid.uuid4())
    r = client.get(f"/api/experiments/{missing}")
    assert r.status_code == 404
