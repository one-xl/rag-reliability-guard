"""Threshold sweep script helpers."""

import json
from pathlib import Path

from scripts.sweep_answer_thresholds import sweep_thresholds, write_outputs


def _write_metadata(path: Path, doc_id: str, chunks: list[tuple[int, str]]) -> None:
    payload = {
        "id": doc_id,
        "original_filename": "sweep.pdf",
        "chunks": [
            {"index": idx, "text": text, "char_count": len(text)} for idx, text in chunks
        ],
    }
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{doc_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_sweep_thresholds_returns_ranked_rows(tmp_path):
    doc_id = "00000000-0000-4000-8000-000000000099"
    docs = tmp_path / "documents"
    _write_metadata(docs, doc_id, [(0, "alpha beta evidence")])
    payload = {
        "method": "keyword",
        "generator": "extractive",
        "top_k": 3,
        "cases": [
            {"question": "alpha beta", "answerable": True, "expected_document_id": doc_id},
            {"question": "unmatched private token", "answerable": False},
        ],
    }

    rows = sweep_thresholds(
        payload,
        docs,
        support_values=[0.3, 0.5],
        overlap_values=[0.2, 0.4],
    )
    assert len(rows) == 4
    assert rows[0]["score"] >= rows[-1]["score"]
    assert {"min_support_rate", "min_relevance_overlap", "score"} <= set(rows[0])


def test_write_outputs_writes_json_and_csv(tmp_path):
    rows = [{"min_support_rate": 0.5, "min_relevance_overlap": 0.4, "score": 1.0}]
    json_path, csv_path = write_outputs(
        rows,
        tmp_path,
        dataset_path=Path("dataset.json"),
        timestamp="20260101_000000",
    )
    assert json_path.name == "threshold_sweep_20260101_000000.json"
    assert csv_path.name == "threshold_sweep_20260101_000000.csv"
    assert json.loads(json_path.read_text(encoding="utf-8"))["best"]["score"] == 1.0
    assert "min_support_rate" in csv_path.read_text(encoding="utf-8")
