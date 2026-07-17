"""RAG API router — corrective RAG with caching, classification, and VRAM-aware routing."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Any

from app.services.rag.service import get_rag_service

router = APIRouter(prefix="/rag", tags=["RAG"])


# ── Schemas ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    tenant_id: str = Field(default="", description="Tenant scope")
    stream: bool = Field(default=False, description="Enable token streaming")


class ChunkItem(BaseModel):
    id: str = Field(..., description="Chunk UUID")
    text: str = Field(..., description="Chunk text content")
    page: int | None = None
    heading: str | None = None
    chunk_index: int = 0
    document_id: str | None = None


class IngestRequest(BaseModel):
    chunks: list[ChunkItem] = Field(..., min_length=1, max_length=500)
    tenant_id: str = Field(..., description="Tenant scope")


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    cache_hit: bool
    model_backend: str
    model_name: str | None = None
    gave_up: bool
    latency_ms: float
    stage_timings_ms: dict[str, float] | None = None
    classification: str | None = None
    corrected: bool | None = None
    retries: int | None = None
    mode: str | None = None
    failure_type: str | None = None
    correction_path: str | None = None


class IngestResponse(BaseModel):
    indexed: int
    tenant_id: str


class CacheStatsResponse(BaseModel):
    cache: dict[str, Any]
    routing: dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest):
    """Execute corrective RAG pipeline: classify → cache check → retrieve →
    correct → route model → generate → cache write."""
    svc = get_rag_service()
    try:
        result = await svc.query(
            question=payload.question,
            tenant_id=payload.tenant_id,
            stream=payload.stream,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest):
    """Index document chunks into Qdrant with dense + sparse vectors."""
    svc = get_rag_service()
    try:
        chunk_dicts = [c.model_dump() for c in payload.chunks]
        result = await svc.ingest(chunks=chunk_dicts, tenant_id=payload.tenant_id)
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def cache_stats():
    """Return semantic cache hit-rate and model routing statistics."""
    svc = get_rag_service()
    return svc.cache_stats()


@router.get("/routing/stats")
async def routing_stats():
    """Return 2-axis routing mode distribution and correction path statistics."""
    svc = get_rag_service()
    return svc.cache_stats()["routing"]


@router.delete("/cache")
async def clear_cache():
    """Clear the semantic cache entirely."""
    from app.services.rag.cache import get_semantic_cache
    cache = get_semantic_cache()
    count = cache.clear()
    return {"cleared": count, "message": f"Removed {count} cache entries"}


# ── Legacy endpoints (preserved from conversations/rag.py) ────────────

from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from sqlalchemy import select
from app.models.conversations.conversation import Conversation, Message


@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch conversation message history."""

    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return {
        "conversation_id": conversation_id,
        "messages": [
            {
                "id": str(msg.id),
                "direction": msg.direction,
                "channel": msg.channel,
                "content": msg.content,
                "is_ai_generated": getattr(msg, "is_ai_generated", None),
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ],
    }


@router.post("/chat")
async def rag_chat_deprecated():
    """Deprecated — use POST /rag/query instead."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This endpoint is deprecated. Use POST /rag/query instead.",
    )
