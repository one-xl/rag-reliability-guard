import csv
import json
from io import StringIO

from scripts.run_answer_eval_experiment import (
    _aggregate_row,
    _baseline_payload,
    _guarded_payload,
    _write_outputs,
)


def test_baseline_payload_removes_guard_fields():
    payload = {
        "method": "bm25",
        "generator": "extractive",
        "top_k": 3,
        "min_support_rate": 0.5,
        "min_relevance_overlap": 0.35,
        "save": True,
        "cases": [],
    }
    out = _baseline_payload(payload)
    assert out["method"] == "bm25"
    assert "min_support_rate" not in out
    assert "min_relevance_overlap" not in out
    assert "save" not in out


def test_guarded_payload_sets_thresholds_without_mutating_input():
    payload = {"cases": [], "min_support_rate": 0.1}
    out = _guarded_payload(payload, min_support_rate=0.5, min_relevance_overlap=0.35)
    assert payload["min_support_rate"] == 0.1
    assert out["min_support_rate"] == 0.5
    assert out["min_relevance_overlap"] == 0.35


def test_aggregate_row_flattens_metrics():
    row = _aggregate_row(
        "guarded",
        {
            "method": "bm25",
            "generator": "extractive",
            "top_k": 3,
            "min_support_rate": 0.5,
            "min_relevance_overlap": 0.35,
            "aggregate": {"total": 2, "refusal_accuracy": 1.0},
        },
    )
    assert row["name"] == "guarded"
    assert row["method"] == "bm25"
    assert row["total"] == 2
    assert row["refusal_accuracy"] == 1.0


def test_write_outputs_creates_comparison_json_and_csv(tmp_path):
    results = {
        "baseline": {
            "method": "bm25",
            "generator": "extractive",
            "top_k": 3,
            "aggregate": {"total": 1, "citation_hit_rate": 1.0},
        },
        "guarded": {
            "method": "bm25",
            "generator": "extractive",
            "top_k": 3,
            "min_support_rate": 0.5,
            "min_relevance_overlap": 0.35,
            "aggregate": {"total": 1, "refusal_accuracy": 1.0},
        },
    }
    json_path, csv_path = _write_outputs(
        tmp_path,
        "20260101_000000",
        tmp_path / "cases.json",
        results,
    )
    record = json.loads(json_path.read_text(encoding="utf-8"))
    assert record["results"]["guarded"]["min_relevance_overlap"] == 0.35

    rows = list(csv.DictReader(StringIO(csv_path.read_text(encoding="utf-8"))))
    assert [row["name"] for row in rows] == ["baseline", "guarded"]
