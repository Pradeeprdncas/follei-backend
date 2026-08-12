"""Retrieval-augmented generation orchestration for the knowledge query API."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.config.settings import Settings, get_settings
from app.services.knowledge.llm_service import get_llm_service
from app.services.knowledge.retrieval_service import (
    KnowledgeRetrievalService,
    RetrievedChunk,
    assemble_context_prompt,
)


@dataclass(frozen=True)
class PreparedKnowledgeQuery:
    prompt: str
    chunks: list[RetrievedChunk]


class TextGenerator(Protocol):
    def generate(self, prompt: str, stream: bool = True) -> AsyncIterator[str]: ...


class KnowledgeQueryService:
    def __init__(
        self,
        *,
        retrieval: KnowledgeRetrievalService | None = None,
        llm: TextGenerator | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retrieval = retrieval or KnowledgeRetrievalService(settings=self.settings)
        self.llm = llm or get_llm_service(settings=self.settings)

    async def prepare(
        self,
        *,
        query: str,
        tenant_id: str,
        category: str | None,
        top_k: int | None,
        include_unreviewed: bool = False,
        source_ids: list[str] | None = None,
    ) -> PreparedKnowledgeQuery:
        chunks = await self.retrieval.search(
            query,
            tenant_id,
            category=category,
            top_k=top_k or self.settings.KNOWLEDGE_QUERY_TOP_K,
            include_unreviewed=include_unreviewed,
            source_ids=source_ids,
        )
        return PreparedKnowledgeQuery(prompt=assemble_context_prompt(query, chunks), chunks=chunks)
