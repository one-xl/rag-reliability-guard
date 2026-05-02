import json

import pytest
from fastapi.testclient import TestClient

from app.external_eval import (
    evaluate_external_answer_case,
    evaluate_external_answer_cases,
    is_refusal,
)
from app.main import app
from scripts.evaluate_external_answers import load_payload, write_result


def test_is_refusal_detects_english_and_chinese_refusals():
    assert is_refusal("I cannot answer because there is not enough information.")
    assert is_refusal("知识库中没有足够信息，暂时无法回答。")
    assert not is_refusal("RAG uses retrieved evidence.")
    assert not is_refusal("The paper does not have enough information about X.")
    assert not is_refusal("I don't know if it improves retrieval quality.")


def test_evaluate_external_answer_case_supported_answer():
    row = evaluate_external_answer_case(
        {
            "case_id": "c1",
            "question": "What does RAG use?",
            "answerable": True,
            "answer": "RAG uses retrieved evidence.",
            "evidence": [
                {
                    "evidence_id": "doc#1",
                    "text": "RAG uses retrieved evidence before generating an answer.",
                    "source": "doc.md",
                }
            ],
        },
        min_support_rate=0.5,
    )
    assert row["case_id"] == "c1"
    assert row["answerable"] is True
    assert row["refused"] is False
    assert row["over_refusal"] is False
    assert row["support_rate"] >= 0.5
    assert row["unsupported_claim_rate"] <= 0.5
    assert row["hallucination_proxy_rate"] <= 0.5
    assert row["reliable"] is True
    assert row["model"] == "unknown"
    assert row["provider"] == "unknown"
    assert row["run_id"] is None


def test_evaluate_external_answer_case_over_refusal():
    row = evaluate_external_answer_case(
        {
            "question": "What metric measures refusal?",
            "answerable": True,
            "answer": "I cannot answer because there is not enough information.",
            "evidence": [
                {
                    "evidence_id": "doc#2",
                    "text": "Refusal accuracy measures correct refusal.",
                }
            ],
        },
        min_support_rate=0.5,
    )
    assert row["refused"] is True
    assert row["over_refusal"] is True
    assert row["reliable"] is False


def test_evaluate_external_answer_cases_aggregate_counts():
    out = evaluate_external_answer_cases(
        [
            {
                "question": "What does RAG use?",
                "answerable": True,
                "answer": "RAG uses retrieved evidence.",
                "evidence": [{"text": "RAG uses retrieved evidence."}],
            },
            {
                "question": "What is the private key?",
                "answerable": False,
                "answer": "I cannot answer because there is not enough information.",
                "evidence": [],
            },
            {
                "question": "What metric measures refusal?",
                "answerable": True,
                "answer": "I cannot answer because there is not enough information.",
                "evidence": [{"text": "Refusal accuracy measures correct refusal."}],
            },
        ],
        min_support_rate=0.5,
    )
    agg = out["aggregate"]
    assert agg["total"] == 3
    assert agg["answerable_total"] == 2
    assert agg["unanswerable_total"] == 1
    assert agg["refusal_accuracy"] == 1.0
    assert agg["over_refusal_rate"] == 0.5
    assert "by_model" in agg
    assert len(agg["by_model"]) == 1
    u = agg["by_model"]["unknown/unknown"]
    assert u["total"] == 3
    assert u["answerable_total"] == 2
    assert u["unanswerable_total"] == 1
    assert u["refusal_accuracy"] == 1.0
    assert u["over_refusal_rate"] == 0.5


def test_evaluate_external_answer_case_optional_metadata_defaults_unknown():
    row = evaluate_external_answer_case(
        {
            "question": "q",
            "answerable": True,
            "answer": "a",
            "evidence": [{"text": "a"}],
        },
    )
    assert row["model"] == "unknown"
    assert row["provider"] == "unknown"
    assert row["run_id"] is None


def test_evaluate_external_answer_case_optional_metadata_and_run_id():
    row = evaluate_external_answer_case(
        {
            "question": "q",
            "answerable": True,
            "answer": "a",
            "evidence": [{"text": "a"}],
            "model": "gpt-4.1-mini",
            "provider": "openai",
            "run_id": "exp-001",
        },
    )
    assert row["model"] == "gpt-4.1-mini"
    assert row["provider"] == "openai"
    assert row["run_id"] == "exp-001"


def test_evaluate_external_answer_cases_by_model_aggregate():
    out = evaluate_external_answer_cases(
        [
            {
                "question": "What does RAG use?",
                "answerable": True,
                "answer": "RAG uses retrieved evidence.",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "evidence": [{"text": "RAG uses retrieved evidence before generating an answer."}],
            },
            {
                "question": "What metric measures refusal?",
                "answerable": True,
                "answer": "I cannot answer because there is not enough information.",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "evidence": [{"text": "Refusal accuracy measures correct refusal."}],
            },
            {
                "question": "What is the private key?",
                "answerable": False,
                "answer": "I cannot answer because there is not enough information.",
                "provider": "volcengine",
                "model": "doubao-pro",
                "evidence": [],
            },
        ],
        min_support_rate=0.5,
    )
    by_model = out["aggregate"]["by_model"]
    assert set(by_model) == {"openai/gpt-4.1-mini", "volcengine/doubao-pro"}
    o = by_model["openai/gpt-4.1-mini"]
    assert o["total"] == 2
    assert o["answerable_total"] == 2
    assert o["unanswerable_total"] == 0
    assert o["refusal_accuracy"] == 0.0
    assert o["over_refusal_rate"] == 0.5
    v = by_model["volcengine/doubao-pro"]
    assert v["total"] == 1
    assert v["unanswerable_total"] == 1
    assert v["refusal_accuracy"] == 1.0
    assert v["over_refusal_rate"] == 0.0


def test_evaluate_external_answer_cases_rejects_bad_payload():
    with pytest.raises(ValueError, match="cases must be a list"):
        evaluate_external_answer_cases("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="answerable"):
        evaluate_external_answer_cases([{"question": "x", "answer": "y"}])


def test_external_answer_api_success():
    client = TestClient(app)
    response = client.post(
        "/api/evaluate/external-answer",
        json={
            "question": "What does RAG use?",
            "answerable": True,
            "answer": "RAG uses retrieved evidence.",
            "evidence": [{"text": "RAG uses retrieved evidence."}],
            "min_support_rate": 0.5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["support_rate"] >= 0.5
    assert body["reliable"] is True
    assert body["model"] == "unknown"
    assert body["provider"] == "unknown"


def test_external_answers_api_success():
    client = TestClient(app)
    response = client.post(
        "/api/evaluate/external-answers",
        json={
            "min_support_rate": 0.5,
            "cases": [
                {
                    "question": "What does RAG use?",
                    "answerable": True,
                    "answer": "RAG uses retrieved evidence.",
                    "evidence": [{"text": "RAG uses retrieved evidence."}],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["aggregate"]["total"] == 1
    assert "by_model" in body["aggregate"]
    assert "unknown/unknown" in body["aggregate"]["by_model"]
    assert body["aggregate"]["by_model"]["unknown/unknown"]["total"] == 1


def test_external_answers_api_rejects_invalid_cases():
    client = TestClient(app)
    response = client.post("/api/evaluate/external-answers", json={"cases": "bad"})
    assert response.status_code == 400
    assert "cases" in response.json()["detail"]


def test_external_eval_script_helpers(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps({"cases": [{"question": "q", "answer": "a", "answerable": True}]}),
        encoding="utf-8",
    )
    payload = load_payload(dataset)
    assert len(payload["cases"]) == 1

    out = write_result(
        {
            "rows": [],
            "aggregate": {"total": 0, "by_model": {}},
        },
        dataset_path=dataset,
        output_dir=tmp_path,
        timestamp="20260101_000000",
    )
    assert out.name == "external_eval_20260101_000000.json"
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["dataset"].endswith("cases.json")
    assert record["aggregate"]["by_model"] == {}
