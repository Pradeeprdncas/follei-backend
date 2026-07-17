"""Minimal tenant-scoped source and business-fact review APIs."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.database.session import get_db
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.fact_publishing import publish_fact_draft
from app.services.knowledge.graph import sync_approved_fact_to_graph
from app.services.knowledge.outbox import enqueue_sync_event
from app.core.security import get_authenticated_tenant_id, require_matching_tenant
from app.repositories.chunk import ChunkRepository
from app.services.rag.retrieval.approval import approval_tag_for

router = APIRouter(prefix="/knowledge/review", tags=["knowledge-review"])
_settings = get_settings()


class ReviewAction(BaseModel):
    tenant_id: str
    reviewer: str = Field(default="human")
    reason: str | None = None


def _draft_response(draft: BusinessFactDraft) -> dict:
    return {
        "id": str(draft.id),
        "tenant_id": str(draft.tenant_id),
        "document_id": str(draft.document_id),
        "chunk_id": str(draft.chunk_id) if draft.chunk_id else None,
        "fact_type": draft.fact_type,
        "payload": draft.payload,
        "citation": draft.citation,
        "extraction_confidence": float(draft.extraction_confidence) if draft.extraction_confidence is not None else None,
        "approval_status": draft.approval_status,
        "reviewer": draft.reviewer,
        "review_reason": draft.review_reason,
        "published_record_type": draft.published_record_type,
        "published_record_id": str(draft.published_record_id) if draft.published_record_id else None,
        "created_at": draft.created_at,
        "reviewed_at": draft.reviewed_at,
    }


@router.get("/facts/drafts")
def list_fact_drafts(
    tenant_id: UUID,
    status: str = "draft",
    limit: int = 50,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """List a tenant's extracted facts with their source citations."""
    require_matching_tenant(tenant_id, authenticated_tenant_id)
    rows = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.tenant_id == tenant_id,
        BusinessFactDraft.approval_status == status,
    ).order_by(BusinessFactDraft.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [_draft_response(row) for row in rows]


@router.get("/facts/{draft_id}")
def get_fact_draft(draft_id: UUID, tenant_id: UUID, db: Session = Depends(get_db)):
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == tenant_id,
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Fact draft not found for tenant")
    return _draft_response(draft)


@router.post("/facts/{draft_id}/approve")
def approve_fact_draft(
    draft_id: UUID,
    action: ReviewAction,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Publish one reviewed draft to its approved PostgreSQL entity table."""
    require_matching_tenant(action.tenant_id, authenticated_tenant_id)
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == UUID(action.tenant_id),
    ).with_for_update().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Fact draft not found for tenant")
    if draft.approval_status != "draft":
        raise HTTPException(status_code=409, detail=f"Fact draft is already {draft.approval_status}")
    try:
        publish_fact_draft(db, draft)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    draft.approval_status = "approved"
    draft.reviewer = action.reviewer
    draft.review_reason = action.reason
    draft.reviewed_at = datetime.utcnow()
    sync_approved_fact_to_graph(db, draft=draft)
    enqueue_sync_event(
        db,
        tenant_id=draft.tenant_id,
        event_type="fact.approved",
        aggregate_type="business_fact_draft",
        aggregate_id=draft.id,
        idempotency_key=f"fact-approved:{draft.id}",
        payload={"chunk_id": str(draft.chunk_id) if draft.chunk_id else None, "fact_type": draft.fact_type},
    )
    db.commit()
    db.refresh(draft)
    return _draft_response(draft)


@router.post("/facts/{draft_id}/reject")
def reject_fact_draft(draft_id: UUID, action: ReviewAction, db: Session = Depends(get_db)):
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == UUID(action.tenant_id),
    ).with_for_update().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Fact draft not found for tenant")
    if draft.approval_status != "draft":
        raise HTTPException(status_code=409, detail=f"Fact draft is already {draft.approval_status}")
    draft.approval_status = "rejected"
    draft.reviewer = action.reviewer
    draft.review_reason = action.reason
    draft.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    return _draft_response(draft)


# Existing Qdrant source-chunk review endpoints. They remain separate from fact approval.
@router.get("/drafts")
def list_drafts(tenant_id: str, limit: int = 50):
    points, _ = get_qdrant().scroll(
        collection_name=_settings.QDRANT_COLLECTION_NAME,
        scroll_filter={"must": [{"key": "tenant_id", "match": {"value": tenant_id}}, {"key": "approval_status", "match": {"value": "draft"}}]},
        limit=max(1, min(limit, 200)),
        with_payload=True,
    )
    return [{"chunk_id": str(point.id), "tenant_id": tenant_id, **(point.payload or {})} for point in points]


@router.post("/{chunk_id}/approve")
def approve_draft(chunk_id: str, action: ReviewAction, db: Session = Depends(get_db)):
    return _set_status(chunk_id, action, "approved", db)


@router.post("/{chunk_id}/reject")
def reject_draft(chunk_id: str, action: ReviewAction, db: Session = Depends(get_db)):
    return _set_status(chunk_id, action, "rejected", db)


def _set_status(chunk_id: str, action: ReviewAction, status: str, db: Session):
    client = get_qdrant()
    points = client.retrieve(collection_name=_settings.QDRANT_COLLECTION_NAME, ids=[chunk_id], with_payload=True)
    if not points or (points[0].payload or {}).get("tenant_id") != action.tenant_id:
        raise HTTPException(status_code=404, detail="Draft not found for tenant")
    payload = {"approval_status": status, "reviewer": action.reviewer}
    if action.reason:
        payload["review_reason"] = action.reason
    client.set_payload(collection_name=_settings.QDRANT_COLLECTION_NAME, points=[chunk_id], payload=payload)
    # Keep the Postgres chunk's approval tag in sync with Qdrant so BM25 and
    # neighbor expansion (which read Postgres, not Qdrant) agree on what's approved.
    chunk_repo = ChunkRepository(db)
    chunk = chunk_repo.get_by_id(chunk_id)
    if chunk:
        remaining_tags = [t for t in (chunk.tags or []) if not t.startswith("approval:")]
        chunk_repo.set_tags(chunk_id, remaining_tags + [approval_tag_for(status)])
    return {"chunk_id": chunk_id, "tenant_id": action.tenant_id, "approval_status": status, "reviewer": action.reviewer}


