"""豆包 OpenAI-compatible client tests."""

import httpx
import pytest

from app.config import DoubaoSettings
from app.llm_client import (
    LLMConfigurationError,
    LLMRequestError,
    build_doubao_messages,
    generate_doubao_answer,
)


def test_build_doubao_messages_contains_question_and_citations():
    messages = build_doubao_messages(
        "RAG 是什么？",
        [
            {
                "index": 1,
                "original_filename": "notes.pdf",
                "chunk_index": 2,
                "text_preview": "RAG 使用检索证据回答问题。",
            }
        ],
    )
    assert messages[0]["role"] == "system"
    assert "RAG 是什么？" in messages[1]["content"]
    assert "[1]" in messages[1]["content"]
    assert "notes.pdf" in messages[1]["content"]


def test_generate_doubao_answer_rejects_placeholder_settings():
    settings = DoubaoSettings(
        api_key="your_ark_api_key_here",
        base_url="https://example.test/api/v3",
        model="your_doubao_endpoint_or_model_id_here",
        timeout_seconds=1,
    )
    with pytest.raises(LLMConfigurationError):
        generate_doubao_answer("q", [], settings=settings)


def test_generate_doubao_answer_posts_openai_compatible_payload(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            calls["url"] = url
            calls["headers"] = headers
            calls["json"] = json
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "基于证据回答 [1]"}}]},
                request=request,
            )

    monkeypatch.setattr("app.llm_client.httpx.Client", FakeClient)
    settings = DoubaoSettings(
        api_key="test_key",
        base_url="https://example.test/api/v3/",
        model="doubao-test",
        timeout_seconds=12,
    )
    answer = generate_doubao_answer(
        "什么是 RAG？",
        [
            {
                "index": 1,
                "original_filename": "rag.pdf",
                "chunk_index": 0,
                "text_preview": "RAG 是检索增强生成。",
            }
        ],
        settings=settings,
    )
    assert answer == "基于证据回答 [1]"
    assert calls["timeout"] == 12
    assert calls["url"] == "https://example.test/api/v3/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer test_key"
    assert calls["json"]["model"] == "doubao-test"
    assert calls["json"]["temperature"] == 0.2


def test_generate_doubao_answer_retries_5xx_then_succeeds(monkeypatch):
    calls = {"count": 0, "sleeps": []}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            calls["count"] += 1
            request = httpx.Request("POST", url)
            if calls["count"] == 1:
                return httpx.Response(503, text="temporarily unavailable", request=request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "重试后成功 [1]"}}]},
                request=request,
            )

    monkeypatch.setattr("app.llm_client.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "app.llm_client.time.sleep",
        lambda seconds: calls["sleeps"].append(seconds),
    )
    settings = DoubaoSettings(
        api_key="test_key",
        base_url="https://example.test/api/v3",
        model="doubao-test",
        timeout_seconds=12,
    )
    answer = generate_doubao_answer(
        "q",
        [],
        settings=settings,
        max_retries=1,
        retry_backoff_seconds=0.01,
    )
    assert answer == "重试后成功 [1]"
    assert calls["count"] == 2
    assert calls["sleeps"] == [0.01]


def test_generate_doubao_answer_does_not_retry_4xx(monkeypatch):
    calls = {"count": 0}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            calls["count"] += 1
            request = httpx.Request("POST", url)
            return httpx.Response(401, text="unauthorized", request=request)

    monkeypatch.setattr("app.llm_client.httpx.Client", FakeClient)
    settings = DoubaoSettings(
        api_key="test_key",
        base_url="https://example.test/api/v3",
        model="doubao-test",
        timeout_seconds=12,
    )
    with pytest.raises(LLMRequestError):
        generate_doubao_answer("q", [], settings=settings, max_retries=2)
    assert calls["count"] == 1
