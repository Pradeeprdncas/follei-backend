"""Audit and repair approved-fact publication/approval consistency."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.domain import Policy
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.repositories.chunk import ChunkRepository
from app.services.knowledge.fact_publishing import canonicalize_fact_payload
from app.services.rag.retrieval.approval import approval_tag_for


@dataclass(frozen=True)
class ApprovalInconsistency:
    tenant_id: str
    draft_id: str
    chunk_id: str | None
    fact_type: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def _policy_for_draft(db: Session, draft: BusinessFactDraft) -> Policy | None:
    if draft.fact_type != "policy" or draft.published_record_type != Policy.__tablename__:
        return None
    if draft.published_record_id:
        return db.query(Policy).filter(
            Policy.id == draft.published_record_id,
            Policy.tenant_id == draft.tenant_id,
        ).first()
    return None


def find_approval_inconsistencies(db: Session) -> tuple[int, list[ApprovalInconsistency]]:
    """Return all approved drafts with a broken policy body or chunk state."""
    drafts = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.approval_status == "approved",
    ).order_by(BusinessFactDraft.created_at.asc()).all()
    chunk_repo = ChunkRepository(db)
    found: list[ApprovalInconsistency] = []
    for draft in drafts:
        reasons: list[str] = []
        if draft.fact_type == "policy":
            policy = _policy_for_draft(db, draft)
            if policy is None:
                reasons.append("operational_policy_missing")
            elif not (policy.body or "").strip():
                reasons.append("operational_policy_body_null")
        if draft.chunk_id:
            chunk = chunk_repo.get_by_id(str(draft.chunk_id))
            if chunk is None:
                reasons.append("source_chunk_missing")
            elif approval_tag_for("approved") not in (chunk.tags or []):
                reasons.append("source_chunk_not_approved")
        if reasons:
            found.append(ApprovalInconsistency(
                tenant_id=str(draft.tenant_id),
                draft_id=str(draft.id),
                chunk_id=str(draft.chunk_id) if draft.chunk_id else None,
                fact_type=draft.fact_type,
                reasons=tuple(reasons),
            ))
    return len(drafts), found


def _reset_fact_approval_event(
    db: Session,
    *,
    draft: BusinessFactDraft,
    approved_tags: list[str] | None,
) -> KnowledgeSyncEvent:
    key = f"fact-approved:{draft.id}"
    event = db.query(KnowledgeSyncEvent).filter(
        KnowledgeSyncEvent.tenant_id == draft.tenant_id,
        KnowledgeSyncEvent.idempotency_key == key,
    ).with_for_update().first()
    payload = {
        **(event.payload if event else {}),
        "chunk_id": str(draft.chunk_id) if draft.chunk_id else None,
        "fact_type": draft.fact_type,
        "approval_status": "approved",
        "reviewer": draft.reviewer or "consistency-backfill",
        "reason": draft.review_reason or "repair legacy fact/chunk approval consistency",
        "tags": approved_tags,
    }
    if event is None:
        event = KnowledgeSyncEvent(
            tenant_id=draft.tenant_id,
            event_type="fact.approved",
            aggregate_type="business_fact_draft",
            aggregate_id=draft.id,
            idempotency_key=key,
            payload=payload,
            deliveries={"postgres": "completed", "qdrant": "pending"},
            status="pending",
        )
        db.add(event)
    else:
        event.event_type = "fact.approved"
        event.aggregate_type = "business_fact_draft"
        event.aggregate_id = draft.id
        event.payload = payload
        event.deliveries = {"postgres": "completed", "qdrant": "pending"}
        event.status = "pending"
        event.last_error = None
        event.completed_at = None
        event.updated_at = datetime.utcnow()
    db.flush()
    return event


def repair_approval_inconsistencies(db: Session) -> dict[str, Any]:
    """Repair every current inconsistency in one PostgreSQL transaction.

    External Qdrant writes are deliberately left to the durable outbox.  If
    delivery is unavailable the database remains correct and the event stays
    retryable rather than partially rolling back reviewed business data.
    """
    scanned, inconsistencies = find_approval_inconsistencies(db)
    repaired: list[dict[str, Any]] = []
    chunk_repo = ChunkRepository(db)
    try:
        for issue in inconsistencies:
            draft = db.query(BusinessFactDraft).filter(
                BusinessFactDraft.id == UUID(issue.draft_id),
                BusinessFactDraft.tenant_id == UUID(issue.tenant_id),
            ).with_for_update().one()
            chunk = chunk_repo.get_by_id(str(draft.chunk_id)) if draft.chunk_id else None
            approved_tags = None
            if chunk is not None:
                approved_tags = [tag for tag in (chunk.tags or []) if not tag.startswith("approval:")]
                approved_tags.append(approval_tag_for("approved"))
                chunk_repo.set_tags(str(chunk.id), approved_tags, commit=False)

            if draft.fact_type == "policy":
                fallback_title = (draft.citation or {}).get("heading") or getattr(chunk, "heading", None)
                canonical = canonicalize_fact_payload(
                    draft.fact_type,
                    draft.payload,
                    fallback_text=getattr(chunk, "content", None),
                    fallback_title=fallback_title,
                )
                validation_body = str(canonical.get("body") or "").strip()
                if not validation_body:
                    raise ValueError(f"Cannot repair policy draft {draft.id}: no source body")
                draft.payload = canonical
                policy = _policy_for_draft(db, draft)
                if policy is None:
                    policy = Policy(
                        tenant_id=draft.tenant_id,
                        title=str(canonical["title"]),
                        body=validation_body,
                        policy_type=canonical.get("policy_type"),
                        metadata_={"fact_draft_id": str(draft.id), "source_citation": draft.citation},
                    )
                    db.add(policy)
                    db.flush()
                    draft.published_record_type = Policy.__tablename__
                    draft.published_record_id = policy.id
                else:
                    policy.title = str(canonical["title"])
                    policy.body = validation_body
                    if canonical.get("policy_type") and not policy.policy_type:
                        policy.policy_type = canonical["policy_type"]

            event = _reset_fact_approval_event(db, draft=draft, approved_tags=approved_tags)
            repaired.append({**issue.to_dict(), "outbox_event_id": str(event.id)})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "approved_drafts_scanned": scanned,
        "inconsistencies_found": len(inconsistencies),
        "postgres_rows_repaired": len(repaired),
        "repairs": repaired,
    }
