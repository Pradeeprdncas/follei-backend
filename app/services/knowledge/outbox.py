"""PostgreSQL outbox for idempotent PostgreSQL/FerretDB/Qdrant synchronization."""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.services.knowledge.memory_store import upsert_document_memory, upsert_summary_memory
from app.services.rag.embeddings.mistral import embed_texts
from app.services.rag.vectorstore.insert import insert_chunks
from app.services.rag.vectorstore.qdrant import ensure_collection

_settings = get_settings()
_TARGETS_BY_EVENT = {
    "conversation.summary.ready": ("ferret", "qdrant"),
    "document.indexed": ("ferret",),
    "fact.approved": ("qdrant",),
    "chunk.reviewed": ("qdrant",),
}
Handler = Callable[[KnowledgeSyncEvent], Any | Awaitable[Any]]


def _uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _deliveries(event_type: str) -> dict[str, str]:
    return {"postgres": "completed", **{target: "pending" for target in _TARGETS_BY_EVENT.get(event_type, ())}}


def enqueue_sync_event(
    db: Session,
    *,
    tenant_id: UUID | str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> KnowledgeSyncEvent:
    """Add an outbox event inside the caller's PostgreSQL transaction."""
    tenant_uuid = _uuid(tenant_id)
    existing = db.query(KnowledgeSyncEvent).filter(
        KnowledgeSyncEvent.tenant_id == tenant_uuid,
        KnowledgeSyncEvent.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return existing
    event = KnowledgeSyncEvent(
        tenant_id=tenant_uuid,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=_uuid(aggregate_id),
        payload=payload,
        deliveries=_deliveries(event_type),
        status="pending",
        idempotency_key=idempotency_key,
    )
    db.add(event)
    db.flush()
    return event


async def _ferret_summary(event: KnowledgeSyncEvent) -> str:
    payload = event.payload or {}
    upsert_summary_memory(
        tenant_id=str(event.tenant_id),
        subject_type=str(payload["subject_type"]),
        subject_id=str(payload["subject_id"]),
        summary_id=str(payload["summary_id"]),
        conversation_id=str(payload["conversation_id"]),
        structured=payload.get("structured"),
        summary_text=str(payload.get("summary") or ""),
    )
    return "completed"


async def _ferret_document(event: KnowledgeSyncEvent) -> str:
    payload = event.payload or {}
    upsert_document_memory(
        tenant_id=str(event.tenant_id),
        document_id=str(event.aggregate_id),
        title=str(payload["title"]),
        source_type=str(payload["source_type"]),
        category=payload.get("category"),
        version=int(payload.get("version") or 1),
        summary=str(payload.get("summary") or ""),
        keywords=list(payload.get("keywords") or []),
        chunk_count=int(payload.get("chunk_count") or 0),
        source_uri=payload.get("source_uri"),
        previous_document_id=payload.get("previous_document_id"),
    )
    return "completed"


async def _qdrant_summary(event: KnowledgeSyncEvent) -> str:
    payload = event.payload or {}
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        return "skipped"
    vector = (await embed_texts([summary]))[0]
    ensure_collection()
    insert_chunks(
        [str(payload["summary_id"])],
        [vector],
        [{
            "text": summary,
            "chunk_id": str(payload["summary_id"]),
            "tenant_id": str(event.tenant_id),
            "conversation_id": str(payload["conversation_id"]),
            "customer_id": payload.get("customer_id"),
            "lead_id": payload.get("lead_id"),
            "source_type": "conversation_summary",
            "approval_status": "approved",
            "sensitivity": "internal",
            "heading": "Conversation summary",
            "heading_path": ["Conversations", "Summary"],
        }],
    )
    return "completed"


async def _qdrant_approved_fact(event: KnowledgeSyncEvent) -> str:
    chunk_id = (event.payload or {}).get("chunk_id")
    if not chunk_id:
        return "skipped"
    payload = event.payload or {}
    qdrant_payload = {
        "approval_status": str(payload.get("approval_status") or "approved"),
        "reviewer": payload.get("reviewer"),
    }
    if payload.get("tags") is not None:
        qdrant_payload["tags"] = list(payload["tags"])
    if event.event_type == "fact.approved":
        qdrant_payload["approved_fact_id"] = str(event.aggregate_id)
    if payload.get("reason"):
        qdrant_payload["review_reason"] = payload["reason"]
    get_qdrant().set_payload(
        collection_name=_settings.QDRANT_COLLECTION_NAME,
        points=[str(chunk_id)],
        payload=qdrant_payload,
    )
    return "completed"


def default_handlers() -> dict[str, Handler]:
    return {
        "ferret": lambda event: _ferret_document(event) if event.event_type == "document.indexed" else _ferret_summary(event),
        "qdrant": lambda event: _qdrant_summary(event) if event.event_type == "conversation.summary.ready" else _qdrant_approved_fact(event),
    }


async def deliver_event(event: KnowledgeSyncEvent, *, handlers: dict[str, Handler] | None = None, checkpoint: Callable[[], None] | None = None) -> KnowledgeSyncEvent:
    """Deliver only unfinished targets. Each successful checkpoint is committed by caller."""
    handlers = handlers or default_handlers()
    deliveries = dict(event.deliveries or _deliveries(event.event_type))
    event.status = "processing"
    event.attempt_count = int(event.attempt_count or 0) + 1
    if checkpoint:
        checkpoint()
    for target, target_status in deliveries.items():
        if target == "postgres" or target_status in {"completed", "skipped"}:
            continue
        handler = handlers.get(target)
        if not handler:
            deliveries[target] = "skipped"
            event.deliveries = deliveries
            if checkpoint:
                checkpoint()
            continue
        try:
            result = handler(event)
            result = await result if inspect.isawaitable(result) else result
            deliveries[target] = "skipped" if result == "skipped" else "completed"
            event.last_error = None
            event.deliveries = deliveries
            if checkpoint:
                checkpoint()
        except Exception as exc:
            deliveries[target] = "failed"
            event.deliveries = deliveries
            event.status = "retrying"
            event.last_error = f"{target}: {exc}"[:4000]
            logger.warning(f"Knowledge sync event={event.id} target={target} failed: {exc}")
            if checkpoint:
                checkpoint()
            return event
    event.deliveries = deliveries
    event.status = "completed" if all(value in {"completed", "skipped"} for value in deliveries.values()) else "retrying"
    if event.status == "completed":
        event.completed_at = datetime.utcnow()
    if checkpoint:
        checkpoint()
    return event


async def process_sync_event(event_id: UUID | str, *, handlers: dict[str, Handler] | None = None) -> KnowledgeSyncEvent | None:
    """Process one event with a database commit after every external-target checkpoint."""
    db = SessionLocal()
    try:
        event = db.query(KnowledgeSyncEvent).filter(KnowledgeSyncEvent.id == _uuid(event_id)).with_for_update().first()
        if not event:
            return None
        def checkpoint() -> None:
            db.add(event)
            db.commit()
            db.refresh(event)
        return await deliver_event(event, handlers=handlers, checkpoint=checkpoint)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def process_pending_events(*, limit: int = 25) -> int:
    """Claim and retry pending events; each event maintains its own durable checkpoints."""
    db = SessionLocal()
    try:
        ids = [row.id for row in db.query(KnowledgeSyncEvent.id).filter(
            KnowledgeSyncEvent.status.in_(("pending", "retrying", "processing")),
        ).order_by(KnowledgeSyncEvent.created_at.asc()).limit(max(1, min(limit, 200))).all()]
    finally:
        db.close()
    for event_id in ids:
        await process_sync_event(event_id)
    return len(ids)


def run_pending_events_once() -> int:
    return asyncio.run(process_pending_events())
