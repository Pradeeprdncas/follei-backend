"""Durable read API for RAG conversation history."""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.knowledge.conversation_memory import get_conversation_history
from app.core.security import get_authenticated_tenant_id, require_matching_tenant

router = APIRouter(prefix="/knowledge/conversations", tags=["knowledge-conversations"])


@router.get("/{conversation_id}")
def conversation_history(conversation_id: UUID, tenant_id: UUID, limit: int = 50, db: Session = Depends(get_db)):
    result = get_conversation_history(db, tenant_id=tenant_id, conversation_id=conversation_id, limit=limit)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found for tenant")
    return result

class TurnRequest(BaseModel):
    tenant_id: UUID
    conversation_id: UUID | None = None
    session_id: str | None = None
    customer_id: UUID | None = None
    lead_id: UUID | None = None
    channel: str = Field(..., min_length=1, max_length=32)
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    speaker: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1)
    timestamp: datetime | None = None
    sentiment: str | None = None
    intent: str | None = None
    entities_mentioned: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(None, max_length=160)


@router.post("/turns")
async def persist_turn(
    payload: TurnRequest,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(payload.tenant_id, authenticated_tenant_id)
    from app.services.knowledge.conversation_memory import persist_structured_turn, summarize_conversation
    conversation, message, created = persist_structured_turn(db, **payload.model_dump())
    summary = await summarize_conversation(tenant_id=payload.tenant_id, conversation_id=conversation.id)
    return {"conversation_id": str(conversation.id), "message_id": str(message.id), "created": created, "summary_id": str(summary.id) if summary else None}


@router.post("/{conversation_id}/close")
async def close_conversation(conversation_id: UUID, tenant_id: UUID, db: Session = Depends(get_db)):
    from datetime import datetime
    from app.models.conversations.conversation import Conversation
    from app.services.knowledge.conversation_memory import summarize_conversation
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found for tenant")
    conversation.status = "closed"
    conversation.ended_at = datetime.utcnow()
    db.commit()
    summary = await summarize_conversation(tenant_id=tenant_id, conversation_id=conversation.id, force=True)
    return {"conversation_id": str(conversation.id), "status": "closed", "summary_id": str(summary.id) if summary else None}


