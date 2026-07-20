"""Minimal tenant-scoped source and business-fact review APIs."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.fact_publishing import publish_fact_draft
from app.services.knowledge.fact_extraction import validate_fact_payload
from app.services.knowledge.graph import sync_approved_fact_to_graph, supersede_fact_in_graph
from app.services.knowledge.outbox import enqueue_sync_event
from app.core.security import get_authenticated_tenant_id, require_matching_tenant
from app.repositories.chunk import ChunkRepository
from app.services.rag.retrieval.approval import approval_tag_for

router = APIRouter(prefix="/knowledge/review", tags=["knowledge-review"])


class ReviewAction(BaseModel):
    tenant_id: str
    reviewer: str = Field(default="human")
    reason: str | None = None


class ConflictResolution(BaseModel):
    tenant_id: UUID
    winner_fact_id: UUID
    superseded_fact_ids: list[UUID] = Field(min_length=1, max_length=20)
    reviewer: str = Field(default="human")
    reason: str = Field(min_length=1, max_length=1000)


class FactDraftUpdate(BaseModel):
    """A human-reviewed replacement for an extractor payload before approval."""
    tenant_id: UUID
    payload: dict
    reviewer: str = Field(default="human")
    reason: str = Field(min_length=1, max_length=1000)


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
def get_fact_draft(
    draft_id: UUID,
    tenant_id: UUID,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(tenant_id, authenticated_tenant_id)
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == tenant_id,
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Fact draft not found for tenant")
    return _draft_response(draft)


@router.patch("/facts/{draft_id}")
def update_fact_draft(
    draft_id: UUID,
    action: FactDraftUpdate,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Correct or enrich an extracted fact while preserving review provenance."""
    require_matching_tenant(action.tenant_id, authenticated_tenant_id)
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == action.tenant_id,
    ).with_for_update().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Fact draft not found for tenant")
    if draft.approval_status != "draft":
        raise HTTPException(status_code=409, detail=f"Only draft facts may be edited; current status is {draft.approval_status}")
    validation_error = validate_fact_payload(draft.fact_type, action.payload)
    if validation_error:
        raise HTTPException(status_code=422, detail=validation_error)
    draft.payload = dict(action.payload)
    draft.reviewer = action.reviewer
    draft.review_reason = action.reason
    db.commit()
    db.refresh(draft)
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
    approved_chunk_tags = None
    if draft.chunk_id:
        chunk_repo = ChunkRepository(db)
        chunk = chunk_repo.get_by_id(str(draft.chunk_id))
        if chunk:
            remaining_tags = [tag for tag in (chunk.tags or []) if not tag.startswith("approval:")]
            approved_chunk_tags = remaining_tags + [approval_tag_for("approved")]
            chunk_repo.set_tags(str(chunk.id), approved_chunk_tags, commit=False)
    sync_approved_fact_to_graph(db, draft=draft)
    enqueue_sync_event(
        db,
        tenant_id=draft.tenant_id,
        event_type="fact.approved",
        aggregate_type="business_fact_draft",
        aggregate_id=draft.id,
        idempotency_key=f"fact-approved:{draft.id}",
        payload={
            "chunk_id": str(draft.chunk_id) if draft.chunk_id else None,
            "fact_type": draft.fact_type,
            "approval_status": "approved",
            "reviewer": action.reviewer,
            "reason": action.reason,
            "tags": approved_chunk_tags,
        },
    )
    db.commit()
    db.refresh(draft)
    return _draft_response(draft)


@router.post("/facts/{draft_id}/reject")
def reject_fact_draft(
    draft_id: UUID,
    action: ReviewAction,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(action.tenant_id, authenticated_tenant_id)
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
def list_drafts(
    tenant_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(tenant_id, authenticated_tenant_id)
    chunks = ChunkRepository(db).get_by_tenant(tenant_id)
    return [
        {"chunk_id": str(chunk.id), "tenant_id": tenant_id, "approval_status": "draft", "tags": chunk.tags or []}
        for chunk in chunks
        if approval_tag_for("draft") in (chunk.tags or [])
    ][:max(1, min(limit, 200))]


@router.post("/{chunk_id}/approve")
def approve_draft(
    chunk_id: str,
    action: ReviewAction,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(action.tenant_id, authenticated_tenant_id)
    return _set_status(chunk_id, action, "approved", db)


@router.post("/{chunk_id}/reject")
def reject_draft(
    chunk_id: str,
    action: ReviewAction,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(action.tenant_id, authenticated_tenant_id)
    return _set_status(chunk_id, action, "rejected", db)


def _set_status(chunk_id: str, action: ReviewAction, status: str, db: Session):
    chunk_repo = ChunkRepository(db)
    chunk = chunk_repo.get_by_id(chunk_id)
    if not chunk or str(chunk.tenant_id) != action.tenant_id:
        raise HTTPException(status_code=404, detail="Draft not found for tenant")
    remaining_tags = [t for t in (chunk.tags or []) if not t.startswith("approval:")]
    chunk_repo.set_tags(chunk_id, remaining_tags + [approval_tag_for(status)], commit=False)
    enqueue_sync_event(
        db,
        tenant_id=action.tenant_id,
        event_type="chunk.reviewed",
        aggregate_type="document_chunk",
        aggregate_id=chunk.id,
        idempotency_key=f"chunk-reviewed:{chunk.id}:{status}",
        payload={"chunk_id": chunk_id, "approval_status": status, "reviewer": action.reviewer, "reason": action.reason, "tags": remaining_tags + [approval_tag_for(status)]},
    )
    db.commit()
    return {"chunk_id": chunk_id, "tenant_id": action.tenant_id, "approval_status": status, "reviewer": action.reviewer, "sync_status": "pending"}


@router.post("/conflicts/resolve")
def resolve_fact_conflict(payload: ConflictResolution, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    """Keep one approved operational fact and audibly supersede the losers."""
    require_matching_tenant(payload.tenant_id, authenticated_tenant_id)
    if payload.winner_fact_id in payload.superseded_fact_ids:
        raise HTTPException(status_code=422, detail="Winner cannot also be superseded")
    ids = [payload.winner_fact_id, *payload.superseded_fact_ids]
    drafts = db.query(BusinessFactDraft).filter(BusinessFactDraft.tenant_id == payload.tenant_id, BusinessFactDraft.published_record_id.in_(ids), BusinessFactDraft.approval_status.in_(("approved", "superseded"))).with_for_update().all()
    by_record = {draft.published_record_id: draft for draft in drafts}
    if any(record_id not in by_record for record_id in ids):
        raise HTTPException(status_code=404, detail="One or more approved facts were not found for tenant")
    winner = by_record[payload.winner_fact_id]
    if winner.approval_status != "approved":
        raise HTTPException(status_code=409, detail="Winner must remain an approved fact")
    from app.models.domain import BusinessPlan, Competitor, CustomerSegment, FAQ, Policy, PricingModel, Procedure, Product, Service
    models = {model.__tablename__: model for model in (BusinessPlan, Competitor, CustomerSegment, FAQ, Policy, PricingModel, Procedure, Product, Service)}
    for record_id in payload.superseded_fact_ids:
        draft = by_record[record_id]
        draft.approval_status = "superseded"
        draft.reviewer = payload.reviewer
        draft.review_reason = payload.reason
        draft.reviewed_at = datetime.utcnow()
        model = models.get(draft.published_record_type)
        record = db.query(model).filter(model.id == record_id, model.tenant_id == payload.tenant_id).first() if model else None
        if record:
            if hasattr(record, "metadata_"):
                record.metadata_ = {**(record.metadata_ or {}), "superseded_by": str(payload.winner_fact_id), "superseded_reason": payload.reason}
            elif hasattr(record, "tags"):
                record.tags = [tag for tag in (record.tags or []) if not str(tag).startswith("superseded_by:")] + [f"superseded_by:{payload.winner_fact_id}"]
        supersede_fact_in_graph(db, draft=draft, winner_fact_id=str(payload.winner_fact_id))
        if draft.chunk_id:
            chunk_repo = ChunkRepository(db)
            chunk = chunk_repo.get_by_id(str(draft.chunk_id))
            if chunk:
                remaining_tags = [tag for tag in (chunk.tags or []) if not tag.startswith("approval:")]
                superseded_tags = remaining_tags + [approval_tag_for("superseded")]
                chunk_repo.set_tags(str(chunk.id), superseded_tags, commit=False)
                enqueue_sync_event(
                    db,
                    tenant_id=draft.tenant_id,
                    event_type="chunk.reviewed",
                    aggregate_type="document_chunk",
                    aggregate_id=chunk.id,
                    idempotency_key=f"fact-superseded:{draft.id}:{payload.winner_fact_id}",
                    payload={
                        "chunk_id": str(chunk.id),
                        "approval_status": "superseded",
                        "reviewer": payload.reviewer,
                        "reason": payload.reason,
                        "tags": superseded_tags,
                    },
                )
    db.commit()
    return {"tenant_id": str(payload.tenant_id), "winner_fact_id": str(payload.winner_fact_id), "superseded_fact_ids": [str(value) for value in payload.superseded_fact_ids], "status": "resolved", "winner_draft_id": str(winner.id)}
