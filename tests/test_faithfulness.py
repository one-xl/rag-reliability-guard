"""答案证据支持率与幻觉率评测测试。"""

from fastapi.testclient import TestClient

from app.faithfulness import check_answer_faithfulness, extract_keywords, split_claims
from app.main import app


def test_split_claims():
    assert split_claims("RAG 使用检索。它基于证据回答！") == [
        "RAG 使用检索",
        "它基于证据回答",
    ]


def test_extract_keywords_english_and_chinese():
    kws = extract_keywords("RAG uses retrieval evidence 检索证据")
    assert "rag" in kws
    assert "retrieval" in kws
    assert "检" in kws
    assert "证" in kws


def test_faithfulness_supported_answer():
    result = check_answer_faithfulness(
        "RAG 使用检索证据回答问题。",
        [{"text_preview": "RAG 是检索增强生成，它使用检索证据回答问题。"}],
    )
    assert result["claim_count"] == 1
    assert result["supported_claim_count"] == 1
    assert result["support_rate"] == 1.0
    assert result["hallucination_rate"] == 0.0


def test_faithfulness_flags_unsupported_claim():
    result = check_answer_faithfulness(
        "RAG 使用量子芯片制造疫苗。",
        [{"text_preview": "RAG 是检索增强生成，它使用检索证据回答问题。"}],
    )
    assert result["claim_count"] == 1
    assert result["supported_claim_count"] == 0
    assert result["hallucination_rate"] == 1.0


def test_faithfulness_endpoint():
    client = TestClient(app)
    r = client.post(
        "/api/evaluate/faithfulness",
        json={
            "answer": "RAG 使用检索证据回答问题。",
            "citations": [
                {"text_preview": "RAG 是检索增强生成，它使用检索证据回答问题。"}
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["support_rate"] == 1.0


def test_faithfulness_endpoint_rejects_bad_payload():
    client = TestClient(app)
    r = client.post("/api/evaluate/faithfulness", json={"answer": "", "citations": []})
    assert r.status_code == 400
    r2 = client.post(
        "/api/evaluate/faithfulness",
        json={"answer": "x", "citations": "not-list"},
    )
    assert r2.status_code == 400
