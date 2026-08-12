"""Authenticated, streaming RAG query endpoint."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id
from app.models.integrations.oauth_connection import GoogleWorkspaceConnection
from app.models.knowledge.document import KnowledgeSource
from app.services.integrations.google_workspace_insights import build_gmail_insights
from app.services.knowledge.provider_errors import AIProviderError
from app.services.knowledge.query_service import KnowledgeQueryService, PreparedKnowledgeQuery
from app.services.knowledge.retrieval_service import assemble_context_prompt


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-query"])


class KnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    top_k: int | None = Field(default=None, ge=1, le=20)


class CompanyAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    google_connection_id: UUID
    top_k: int = Field(default=12, ge=4, le=20)


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
            include_unreviewed=False,
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


@router.post("/company-assessment", response_class=StreamingResponse)
async def company_assessment(
    payload: CompanyAssessmentRequest,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
    service: KnowledgeQueryService = Depends(get_knowledge_query_service),
):
    """Stream a review-only assessment over draft ingestion evidence.

    This does not approve facts or unlock autonomous actions. It exists so an
    onboarding user can understand and confirm what Follei extracted before
    those facts become operational knowledge.
    """
    tenant_uuid = UUID(tenant_id)
    connection = db.query(GoogleWorkspaceConnection).filter(
        GoogleWorkspaceConnection.id == payload.google_connection_id,
        GoogleWorkspaceConnection.tenant_id == tenant_uuid,
        GoogleWorkspaceConnection.status == "active",
    ).first()
    if not connection or not connection.source_id:
        raise HTTPException(status_code=404, detail="Google Workspace connection not found")

    gmail = build_gmail_insights(
        db,
        tenant_id=tenant_uuid,
        source_id=connection.source_id,
        account_email=connection.email_address,
    )
    metrics = {
        "classification_method": gmail["classification_method"],
        "counts": gmail["counts"],
        "metrics": gmail["metrics"],
        "observations": gmail["observations"],
    }
    question = (
        "Create a concise onboarding assessment with these sections: What the company appears to do; "
        "recent activity; what is going well; what needs attention; inconsistencies between sources; "
        "and safe ways Follei can help now. Distinguish indexed evidence from inference. Treat every "
        "draft source as unverified and ask the user to confirm uncertain findings. For email, use this "
        f"trusted aggregate analysis rather than inventing thread statistics: {json.dumps(metrics)}"
    )
    website_source_ids = [str(row[0]) for row in db.query(KnowledgeSource.id).filter(
        KnowledgeSource.tenant_id == tenant_uuid,
        KnowledgeSource.source_type == "website",
        KnowledgeSource.is_active.is_(True),
    ).all()]
    google_limit = max(2, payload.top_k // 2)
    website_limit = max(2, payload.top_k - google_limit)
    try:
        google_chunks = await service.retrieval.search(
            question,
            tenant_id,
            top_k=google_limit,
            include_unreviewed=True,
            source_ids=[str(connection.source_id)],
        )
        website_chunks = []
        if website_source_ids:
            website_chunks = await service.retrieval.search(
                question,
                tenant_id,
                top_k=website_limit,
                include_unreviewed=True,
                source_ids=website_source_ids,
            )
        chunks = []
        seen_chunk_ids: set[str] = set()
        for chunk in [*google_chunks, *website_chunks]:
            if chunk.chunk_id not in seen_chunk_ids:
                chunks.append(chunk)
                seen_chunk_ids.add(chunk.chunk_id)
        prepared = PreparedKnowledgeQuery(
            prompt=assemble_context_prompt(question, chunks),
            chunks=chunks,
        )
    except AIProviderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message, "retryable": exc.retryable},
        ) from exc

    async def stream():
        yield _event("analysis", {
            "gmail": gmail,
            "review_mode": True,
            "autonomous_actions_unlocked": False,
            "evidence_coverage": {
                "google_workspace_chunks": len(google_chunks),
                "website_chunks": len(website_chunks),
            },
        })
        yield _event("sources", {"sources": [chunk.public_reference() for chunk in prepared.chunks]})
        try:
            async for token in service.llm.generate(prepared.prompt, stream=True):
                yield _event("token", {"text": token})
            yield _event("done", {"status": "complete", "requires_confirmation": True})
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
