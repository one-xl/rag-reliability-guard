import json

import pytest

from scripts.summarize_external_eval import (
    _latest_external_eval_json,
    load_external_eval,
    render_report_markdown,
    write_report,
)


def _sample_record() -> dict:
    return {
        "created_at": "2026-01-01T12:00:00+08:00",
        "dataset": "datasets/sample_external_answer_eval_cases.json",
        "min_support_rate": 0.5,
        "rows": [],
        "aggregate": {
            "total": 4,
            "answerable_total": 2,
            "unanswerable_total": 2,
            "refusal_correct_count": 2,
            "refusal_accuracy": 1.0,
            "over_refusal_count": 1,
            "over_refusal_rate": 0.5,
            "mean_support_rate": 0.75,
            "mean_hallucination_rate": 0.25,
            "by_model": {
                "openai/gpt-mini": {
                    "total": 2,
                    "answerable_total": 1,
                    "unanswerable_total": 1,
                    "refusal_accuracy": 1.0,
                    "over_refusal_rate": 1.0,
                    "mean_support_rate": 0.8,
                    "mean_hallucination_rate": 0.4,
                },
                "volcengine/doubao": {
                    "total": 2,
                    "answerable_total": 1,
                    "unanswerable_total": 1,
                    "refusal_accuracy": 0.0,
                    "over_refusal_rate": 0.0,
                    "mean_support_rate": 0.7,
                    "mean_hallucination_rate": 0.3,
                },
            },
        },
    }


def test_load_external_eval_reads_json(tmp_path):
    path = tmp_path / "external_eval_20260101_120000.json"
    path.write_text(json.dumps(_sample_record(), ensure_ascii=False), encoding="utf-8")
    loaded = load_external_eval(path)
    assert loaded["dataset"].endswith("sample_external_answer_eval_cases.json")
    assert loaded["aggregate"]["total"] == 4
    assert "openai/gpt-mini" in loaded["aggregate"]["by_model"]


def test_latest_external_eval_json_picks_lexicographically_latest_name(tmp_path):
    (tmp_path / "external_eval_20260101_000000.json").write_text("{}", encoding="utf-8")
    newer = tmp_path / "external_eval_20260201_000000.json"
    newer.write_text("{}", encoding="utf-8")
    picked = _latest_external_eval_json(tmp_path)
    assert picked == newer


def test_render_report_markdown_contains_required_sections():
    md = render_report_markdown(_sample_record())
    assert "# 多模型外部评测报告" in md
    assert "## 实验信息" in md
    assert "datasets/sample_external_answer_eval_cases.json" in md
    assert "## 整体 aggregate 指标" in md
    assert "`refusal_accuracy`" in md
    assert "## 分模型指标（by_model）" in md
    assert "openai/gpt-mini" in md
    assert "volcengine/doubao" in md
    assert "## 模型对比摘要" in md
    assert "refusal_accuracy 最高的模型" in md
    assert "`openai/gpt-mini`" in md
    assert "over_refusal_rate 最高的模型" in md
    assert "mean_hallucination_rate 最低的模型" in md
    assert "`volcengine/doubao`" in md
    assert "## 简短结论" in md


def test_render_report_markdown_does_not_warn_over_refusal_when_all_zero():
    record = _sample_record()
    record["aggregate"]["over_refusal_rate"] = 0.0
    for block in record["aggregate"]["by_model"].values():
        block["over_refusal_rate"] = 0.0
    md = render_report_markdown(record)
    assert "本批分模型 `over_refusal_rate` 均为 0，未观察到过度拒答" in md
    assert "更容易保守拒答" not in md


def test_write_report_creates_file_and_returns_path(tmp_path):
    out = tmp_path / "nested" / "external_report.md"
    path = write_report("hello", out)
    assert path == out
    assert out.read_text(encoding="utf-8") == "hello"


def test_load_external_eval_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(SystemExit, match="must be an object"):
        load_external_eval(path)


def test_load_external_eval_rejects_missing_aggregate(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"dataset": "x"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="aggregate"):
        load_external_eval(path)
