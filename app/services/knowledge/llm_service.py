"""Thin Mistral chat-completion adapter for knowledge generation."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.settings import Settings, get_settings
from app.services.knowledge.provider_errors import (
    ProviderConfigurationError,
    ProviderTimeoutError,
    error_for_status,
)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


class MistralLLMService:
    """Provider boundary for answer generation; callers only see text chunks."""

    def __init__(self, *, settings: Settings | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client
        self.model = self.settings.MISTRAL_CHAT_MODEL

    async def generate(self, prompt: str, stream: bool = True) -> AsyncIterator[str]:
        """Generate answer text; streaming yields provider deltas as they arrive."""
        if not self.settings.MISTRAL_API_KEY:
            raise ProviderConfigurationError()
        if not prompt.strip():
            raise ValueError("Prompt must not be empty")
        if stream:
            async for chunk in self._stream(prompt):
                yield chunk
            return
        yield await self._complete(prompt)

    def _request(self, prompt: str, *, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    async def _complete(self, prompt: str) -> str:
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.settings.MISTRAL_REQUEST_TIMEOUT_SECONDS)
        try:
            try:
                response = await client.post(
                    f"{self.settings.MISTRAL_API_BASE.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.MISTRAL_API_KEY}"},
                    json=self._request(prompt, stream=False),
                )
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError() from exc
            except httpx.RequestError as exc:
                raise error_for_status(503) from exc
            if response.status_code >= 400:
                raise error_for_status(response.status_code)
            try:
                choices = response.json().get("choices", [])
            except (TypeError, ValueError) as exc:
                raise error_for_status(502) from exc
            if not choices:
                raise error_for_status(502)
            return _content_text(choices[0].get("message", {}).get("content"))
        finally:
            if owns_client:
                await client.aclose()
    async def _stream(self, prompt: str) -> AsyncIterator[str]:
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.settings.MISTRAL_REQUEST_TIMEOUT_SECONDS)
        try:
            try:
                async with client.stream(
                    "POST",
                    f"{self.settings.MISTRAL_API_BASE.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.MISTRAL_API_KEY}"},
                    json=self._request(prompt, stream=True),
                ) as response:
                    if response.status_code >= 400:
                        raise error_for_status(response.status_code)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        value = line[5:].strip()
                        if not value or value == "[DONE]":
                            continue
                        try:
                            event = json.loads(value)
                            choices = event.get("choices", [])
                            if choices:
                                text = _content_text(choices[0].get("delta", {}).get("content"))
                                if text:
                                    yield text
                        except (TypeError, ValueError, json.JSONDecodeError) as exc:
                            raise error_for_status(502) from exc
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError() from exc
            except httpx.RequestError as exc:
                raise error_for_status(503) from exc
        finally:
            if owns_client:
                await client.aclose()


def get_llm_service(settings: Settings | None = None) -> MistralLLMService:
    """Provider factory kept beside the adapter for a one-file provider swap."""
    return MistralLLMService(settings=settings)
