"""OpenAI-compatible Doubao chat client."""

from __future__ import annotations

import httpx

from app.config import DoubaoSettings, get_doubao_settings


class LLMConfigurationError(RuntimeError):
    """Raised when Doubao settings are missing or still placeholders."""


class LLMRequestError(RuntimeError):
    """Raised when the provider request fails or returns an unexpected payload."""


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def build_doubao_messages(question: str, citations: list[dict]) -> list[dict]:
    evidence = "\n\n".join(
        f"[{item['index']}] 来源: {item['original_filename']} / chunk {item['chunk_index']}\n"
        f"{item['text_preview']}"
        for item in citations
    )
    return [
        {
            "role": "system",
            "content": (
                "你是一个严谨的检索增强问答助手。只能依据给定证据回答。"
                "关键结论必须带引用编号，例如 [1]。如果证据不足，明确说明无法回答。"
            ),
        },
        {
            "role": "user",
            "content": f"问题：{question}\n\n证据：\n{evidence}",
        },
    ]


def generate_doubao_answer(
    question: str,
    citations: list[dict],
    settings: DoubaoSettings | None = None,
) -> str:
    """Call Doubao through Volcengine Ark's OpenAI-compatible chat endpoint."""
    active_settings = settings or get_doubao_settings()
    if not active_settings.is_configured:
        raise LLMConfigurationError("豆包 API 尚未配置，请检查 .env 中的 DOUBAO_API_KEY 和 DOUBAO_MODEL")

    payload = {
        "model": active_settings.model,
        "messages": build_doubao_messages(question, citations),
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {active_settings.api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=active_settings.timeout_seconds) as client:
            response = client.post(
                _chat_completions_url(active_settings.base_url),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise LLMRequestError(f"豆包 API 请求失败: {exc}") from exc
    except ValueError as exc:
        raise LLMRequestError("豆包 API 返回了无法解析的 JSON") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMRequestError("豆包 API 响应缺少 choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMRequestError("豆包 API 返回了空答案")
    return content.strip()
