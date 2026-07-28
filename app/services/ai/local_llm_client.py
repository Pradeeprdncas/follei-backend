"""Async client for the localhost llama.cpp OpenAI-compatible API."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.settings import get_settings

_settings = get_settings()


class LocalLLMUnavailable(RuntimeError):
    pass


def _payload(messages: list[dict[str, str]], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": _settings.LOCAL_LLM_MODEL,
        "messages": messages,
        "max_tokens": min(_settings.MAX_ANSWER_TOKENS, 768),
        "temperature": 0.15,
        "top_p": 0.9,
    }
    payload.update(overrides)
    return payload


async def complete(messages: list[dict[str, str]], **overrides: Any) -> str:
    try:
        async with httpx.AsyncClient(timeout=_settings.LOCAL_LLM_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{_settings.LOCAL_LLM_BASE_URL}/chat/completions",
                json=_payload(messages, **overrides),
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise LocalLLMUnavailable(f"Local response model is unavailable: {exc}") from exc


async def stream(messages: list[dict[str, str]], **overrides: Any) -> AsyncIterator[str]:
    payload = _payload(messages, stream=True, **overrides)
    try:
        async with httpx.AsyncClient(timeout=_settings.LOCAL_LLM_REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                f"{_settings.LOCAL_LLM_BASE_URL}/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    token = event.get("choices", [{}])[0].get("delta", {}).get("content")
                    if token:
                        yield token
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
        raise LocalLLMUnavailable(f"Local response stream failed: {exc}") from exc
