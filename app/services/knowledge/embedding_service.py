"""Thin Mistral embeddings adapter shared by ingestion and retrieval."""
from __future__ import annotations

import math
import asyncio
from collections.abc import Sequence

import httpx

from app.config.settings import Settings, get_settings
from app.services.knowledge.provider_errors import (
    ProviderConfigurationError,
    ProviderTimeoutError,
    error_for_status,
)


MIN_INGESTION_BATCH_SIZE = 20
MAX_INGESTION_BATCH_SIZE = 50


def embedding_model_name(settings: Settings | None = None) -> str:
    """The sole model-name source used by indexing payloads and query embedding."""
    return (settings or get_settings()).MISTRAL_EMBEDDING_MODEL


class MistralEmbeddingService:
    """Small async adapter over ``POST /v1/embeddings``."""

    def __init__(self, *, settings: Settings | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client
        self.model = embedding_model_name(self.settings)

    async def embed_chunks(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ingestion chunks in configured 20-50 item request batches."""
        if not texts:
            return []
        batch_size = self.settings.MISTRAL_EMBEDDING_BATCH_SIZE
        if not MIN_INGESTION_BATCH_SIZE <= batch_size <= MAX_INGESTION_BATCH_SIZE:
            raise ValueError("MISTRAL_EMBEDDING_BATCH_SIZE must be between 20 and 50")
        # Balance requests so a large ingestion never ends with a tiny remainder.
        # A source containing fewer than 20 total chunks necessarily uses one
        # smaller request.
        batch_count = max(1, math.ceil(len(texts) / batch_size))
        while batch_count > 1 and len(texts) // batch_count < MIN_INGESTION_BATCH_SIZE:
            batch_count -= 1
        base_size, larger_batches = divmod(len(texts), batch_count)
        vectors: list[list[float]] = []
        offset = 0
        for batch_index in range(batch_count):
            current_size = base_size + (1 if batch_index < larger_batches else 0)
            vectors.extend(await self._embed(list(texts[offset : offset + current_size])))
            offset += current_size
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Embed one retrieval query with the exact ingestion embedding model."""
        if not text.strip():
            raise ValueError("Query text must not be empty")
        return (await self._embed([text]))[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.MISTRAL_API_KEY:
            raise ProviderConfigurationError()
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.settings.MISTRAL_REQUEST_TIMEOUT_SECONDS)
        try:
            response: httpx.Response | None = None
            provider_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = await client.post(
                        f"{self.settings.MISTRAL_API_BASE.rstrip('/')}/embeddings",
                        headers={"Authorization": f"Bearer {self.settings.MISTRAL_API_KEY}"},
                        json={"model": self.model, "input": texts},
                    )
                    if response.status_code < 400:
                        provider_error = None
                        break
                    provider_error = error_for_status(response.status_code)
                    if not provider_error.retryable:
                        raise provider_error
                except httpx.TimeoutException as exc:
                    provider_error = ProviderTimeoutError()
                    provider_error.__cause__ = exc
                except httpx.RequestError as exc:
                    provider_error = error_for_status(503)
                    provider_error.__cause__ = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))
            if provider_error is not None:
                raise provider_error
            if response is None:
                raise error_for_status(503)
            try:
                data = response.json().get("data", [])
            except (TypeError, ValueError) as exc:
                raise error_for_status(502) from exc
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
            vectors = [item["embedding"] for item in ordered]
            if len(vectors) != len(texts):
                raise error_for_status(502)
            return vectors
        finally:
            if owns_client:
                await client.aclose()


def get_embedding_service(settings: Settings | None = None) -> MistralEmbeddingService:
    """Provider factory kept in this adapter so retrieval stays provider-neutral."""
    return MistralEmbeddingService(settings=settings)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Compatibility entrypoint for the existing ingestion pipeline."""
    return await get_embedding_service().embed_chunks(texts)


async def embed_query(text: str) -> list[float]:
    """Canonical retrieval-time query embedding entrypoint."""
    return await get_embedding_service().embed_query(text)
