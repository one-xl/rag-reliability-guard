import json

import pytest

from scripts.summarize_answer_eval_comparison import (
    _latest_comparison_json,
    load_comparison,
    render_report_markdown,
    write_report,
)


def _minimal_record() -> dict:
    return {
        "created_at": "2026-01-01T12:00:00+08:00",
        "dataset": "datasets/sample_answer_eval_cases.json",
        "results": {
            "baseline": {
                "method": "bm25",
                "generator": "extractive",
                "top_k": 3,
                "aggregate": {
                    "total": 10,
                    "citation_hit_rate": 0.7,
                    "refusal_accuracy": 0.8,
                    "mean_hallucination_rate": 0.15,
                },
            },
            "guarded": {
                "method": "bm25",
                "generator": "extractive",
                "top_k": 3,
                "min_support_rate": 0.5,
                "min_relevance_overlap": 0.35,
                "aggregate": {
                    "total": 10,
                    "citation_hit_rate": 0.75,
                    "refusal_accuracy": 0.85,
                    "mean_hallucination_rate": 0.1,
                },
            },
        },
    }


def test_load_comparison_reads_json(tmp_path):
    path = tmp_path / "comparison_20260101_120000.json"
    path.write_text(json.dumps(_minimal_record(), ensure_ascii=False), encoding="utf-8")
    loaded = load_comparison(path)
    assert loaded["dataset"].endswith("sample_answer_eval_cases.json")
    assert loaded["results"]["baseline"]["aggregate"]["citation_hit_rate"] == 0.7


def test_render_report_markdown_contains_required_sections():
    md = render_report_markdown(_minimal_record())
    assert "# 答案评测对比实验报告" in md
    assert "## 实验信息" in md
    assert "datasets/sample_answer_eval_cases.json" in md
    assert "## 汇总指标" in md
    assert "## 关键变化" in md
    assert "citation_hit_rate" in md
    assert "refusal_accuracy" in md
    assert "mean_hallucination_rate" in md
    assert "## 简短结论" in md
    assert "Guarded" in md


def test_latest_comparison_json_picks_lexicographically_latest_name(tmp_path):
    (tmp_path / "comparison_20260101_000000.json").write_text("{}", encoding="utf-8")
    newer = tmp_path / "comparison_20260201_000000.json"
    newer.write_text("{}", encoding="utf-8")
    picked = _latest_comparison_json(tmp_path)
    assert picked == newer


def test_write_report_creates_file_and_returns_path(tmp_path):
    out = tmp_path / "nested" / "report.md"
    path = write_report("hello", out)
    assert path == out
    assert out.read_text(encoding="utf-8") == "hello"


def test_load_comparison_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(SystemExit, match="must be an object"):
        load_comparison(path)
