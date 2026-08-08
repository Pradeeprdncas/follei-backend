"""Authenticated, streaming RAG query endpoint."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import get_authenticated_tenant_id
from app.services.knowledge.provider_errors import AIProviderError
from app.services.knowledge.query_service import KnowledgeQueryService


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-query"])


class KnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    top_k: int | None = Field(default=None, ge=1, le=20)


def get_knowledge_query_service() -> KnowledgeQueryService:
    return KnowledgeQueryService()


def _event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.post("/query", response_class=StreamingResponse)
async def query_knowledge(
    payload: KnowledgeQueryRequest,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    service: KnowledgeQueryService = Depends(get_knowledge_query_service),
):
    """Retrieve only the JWT tenant's evidence and stream generated answer tokens as SSE."""
    try:
        prepared = await service.prepare(
            query=payload.query,
            tenant_id=tenant_id,
            category=payload.category,
            top_k=payload.top_k,
        )
    except AIProviderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message, "retryable": exc.retryable},
        ) from exc

    async def stream():
        yield _event("sources", {"sources": [chunk.public_reference() for chunk in prepared.chunks]})
        try:
            async for token in service.llm.generate(prepared.prompt, stream=True):
                yield _event("token", {"text": token})
            yield _event("done", {"status": "complete"})
        except AIProviderError as exc:
            yield _event("error", {
                "code": exc.code,
                "message": exc.public_message,
                "retryable": exc.retryable,
            })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
