"""Durable PostgreSQL conversation history for the RAG chat and voice paths."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.conversations.conversation import Conversation, ConversationCitation, ConversationSummary, Message
from app.services.knowledge.outbox import enqueue_sync_event


class ConversationScopeError(ValueError):
    """A session token exists but belongs to another tenant."""


def _uuid(value: str | UUID | None) -> UUID | None:
    if not value:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def resolve_conversation(db: Session, *, tenant_id: str | UUID, session_id: str | None, title: str, channel: str = "chat") -> Conversation:
    """Resolve a tenant-owned conversation or create a new canonical one."""
    tenant_uuid = _uuid(tenant_id)
    if not tenant_uuid:
        raise ValueError("tenant_id must be a UUID for durable conversation storage")

    conversation: Conversation | None = None
    requested_id = _uuid(session_id)
    if requested_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == requested_id,
            Conversation.tenant_id == tenant_uuid,
        ).first()
        if not conversation:
            other_tenant = db.query(Conversation.id).filter(Conversation.id == requested_id).first()
            if other_tenant:
                raise ConversationScopeError("Conversation does not belong to tenant")
    elif session_id:
        conversation = db.query(Conversation).filter(
            Conversation.tenant_id == tenant_uuid,
            or_(Conversation.public_id == session_id, Conversation.metadata_["external_session_id"].as_string() == session_id),
        ).first()

    if conversation:
        return conversation

    metadata = {"external_session_id": session_id} if session_id else {}
    conversation = Conversation(
        id=requested_id or None,
        tenant_id=tenant_uuid,
        title=title[:180],
        channel=channel,
        status="open",
        started_at=datetime.utcnow(),
        last_activity_at=datetime.utcnow(),
        last_message_at=datetime.utcnow(),
        message_count=0,
        metadata_=metadata,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _rolling_summary(previous: str | None, question: str, answer: str) -> str:
    prior = (previous or "").strip()
    latest = f"Customer asked: {question.strip()[:700]}\nFollei answered: {answer.strip()[:900]}"
    return f"{prior[-1600:]}\n{latest}".strip()[:2600]


def persist_chat_turn(
    db: Session,
    *,
    tenant_id: str | UUID,
    session_id: str | None,
    question: str,
    answer: str,
    citations: list[dict[str, Any]],
    confidence: float,
    supported: bool,
    reason: str,
    channel: str = "chat",
    commit: bool = True,
) -> Conversation:
    """Persist a complete user/assistant exchange, citations, and a rolling summary."""
    conversation = resolve_conversation(db, tenant_id=tenant_id, session_id=session_id, title=question, channel=channel)
    next_sequence = (conversation.message_count or 0) + 1
    user_message = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        role="user",
        content=question,
        message=question,
        sender_type="customer",
        message_type="text",
        direction="inbound",
        speaker="customer",
        channel=channel,
        sequence_number=next_sequence,
        metadata_={},
    )
    assistant_message = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        message=answer,
        sender_type="agent",
        message_type="text",
        direction="outbound",
        speaker="follei",
        channel=channel,
        sequence_number=next_sequence + 1,
        metadata_={"confidence": confidence, "supported": supported, "reason": reason},
    )
    db.add_all((user_message, assistant_message))
    db.flush()

    for citation in citations:
        chunk_id = _uuid(citation.get("chunk_id"))
        if not chunk_id:
            continue
        db.add(ConversationCitation(
            tenant_id=conversation.tenant_id,
            message_id=assistant_message.id,
            chunk_id=chunk_id,
            quote=citation.get("heading") or citation.get("document_name"),
            confidence=confidence,
        ))

    conversation.message_count = next_sequence + 1
    conversation.last_activity_at = datetime.utcnow()
    conversation.last_message_at = conversation.last_activity_at
    conversation.summary = _rolling_summary(conversation.summary, question, answer)
    conversation.analysis_status = "ready"
    conversation.last_analysis_at = datetime.utcnow()
    db.add(ConversationSummary(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        summary_type="rolling",
        summary=conversation.summary,
    ))
    if commit:
        db.commit()
        db.refresh(conversation)
    else:
        db.flush()
    return conversation


def get_conversation_history(db: Session, *, tenant_id: str | UUID, conversation_id: str | UUID, limit: int = 50) -> dict[str, Any] | None:
    tenant_uuid, conversation_uuid = _uuid(tenant_id), _uuid(conversation_id)
    if not tenant_uuid or not conversation_uuid:
        return None
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_uuid,
        Conversation.tenant_id == tenant_uuid,
    ).first()
    if not conversation:
        return None
    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id,
        Message.tenant_id == tenant_uuid,
    ).order_by(Message.sequence_number.asc(), Message.created_at.asc()).limit(max(1, min(limit, 200))).all()
    return {
        "conversation_id": str(conversation.id),
        "tenant_id": str(conversation.tenant_id),
        "channel": conversation.channel,
        "summary": conversation.summary,
        "message_count": conversation.message_count,
        "messages": [{"id": str(message.id), "role": message.role, "content": message.content, "sequence_number": message.sequence_number, "created_at": message.created_at} for message in messages],
    }




# Phase 5 structured multi-channel turn support.
import json
import re
import httpx
from loguru import logger
from app.config.settings import get_settings
from app.config.database import SessionLocal
from app.models.conversations.conversation import ConversationIntent, ConversationSentiment, ConversationEntity

_settings = get_settings()


def _turn_analysis(text: str, sentiment: str | None = None, intent: str | None = None, entities: list[str] | None = None) -> tuple[str, str, list[str]]:
    value = text.lower()
    inferred_sentiment = sentiment or ("negative" if any(word in value for word in ("issue", "problem", "expensive", "worried", "bad")) else "positive" if any(word in value for word in ("thanks", "great", "good", "love")) else "neutral")
    inferred_intent = intent or ("pricing" if any(word in value for word in ("price", "budget", "cost", "quote")) else "comparison" if any(word in value for word in ("competitor", "versus", "vs ")) else "support" if any(word in value for word in ("issue", "problem", "help")) else "general")
    inferred_entities = entities if entities is not None else list(dict.fromkeys(re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", text)))[:12]
    return inferred_sentiment, inferred_intent, inferred_entities


def persist_structured_turn(db: Session, *, tenant_id: str | UUID, conversation_id: str | UUID | None, session_id: str | None, customer_id: str | UUID | None, lead_id: str | UUID | None, channel: str, direction: str, speaker: str, text: str, timestamp: datetime | None = None, sentiment: str | None = None, intent: str | None = None, entities_mentioned: list[str] | None = None, idempotency_key: str | None = None) -> tuple[Conversation, Message, bool]:
    """Idempotently persist one inbound/outbound turn from any Follei channel."""
    tenant_uuid = _uuid(tenant_id)
    if not tenant_uuid:
        raise ValueError("tenant_id must be a UUID for durable conversation storage")
    if idempotency_key:
        existing = db.query(Message).filter(Message.tenant_id == tenant_uuid, Message.idempotency_key == idempotency_key).first()
        if existing:
            conversation = db.query(Conversation).filter(Conversation.id == existing.conversation_id, Conversation.tenant_id == tenant_uuid).first()
            if not conversation:
                raise ConversationScopeError("Existing turn does not belong to tenant")
            return conversation, existing, False
    conversation = resolve_conversation(db, tenant_id=tenant_uuid, session_id=str(conversation_id or session_id) if (conversation_id or session_id) else None, title=text, channel=channel)
    if customer_id and not conversation.customer_id:
        conversation.customer_id = _uuid(customer_id)
    if lead_id and not conversation.lead_id:
        conversation.lead_id = _uuid(lead_id)
    resolved_sentiment, resolved_intent, resolved_entities = _turn_analysis(text, sentiment, intent, entities_mentioned)
    sequence = (conversation.message_count or 0) + 1
    message = Message(tenant_id=tenant_uuid, conversation_id=conversation.id, role="assistant" if direction == "outbound" else "user", content=text, message=text, sender_type=speaker, message_type="text", direction=direction, speaker=speaker, channel=channel, sequence_number=sequence, idempotency_key=idempotency_key, created_at=timestamp or datetime.utcnow(), metadata_={"sentiment": resolved_sentiment, "intent": resolved_intent, "entities_mentioned": resolved_entities})
    db.add(message)
    db.flush()
    db.add(ConversationSentiment(tenant_id=tenant_uuid, conversation_id=conversation.id, message_id=message.id, sentiment=resolved_sentiment, score=0.6))
    db.add(ConversationIntent(tenant_id=tenant_uuid, conversation_id=conversation.id, intent=resolved_intent, evidence=text[:800], confidence=0.6))
    for entity in resolved_entities:
        db.add(ConversationEntity(tenant_id=tenant_uuid, conversation_id=conversation.id, entity_text=entity, entity_type="mentioned", confidence=0.5))
    conversation.message_count = sequence
    conversation.last_activity_at = timestamp or datetime.utcnow()
    conversation.last_message_at = conversation.last_activity_at
    db.commit()
    db.refresh(conversation)
    return conversation, message, True


async def summarize_conversation(*, tenant_id: str | UUID, conversation_id: str | UUID, force: bool = False) -> ConversationSummary | None:
    """Retry-safe structured LLM summary; a failure never rolls back committed turns."""
    db = SessionLocal()
    try:
        tenant_uuid, conversation_uuid = _uuid(tenant_id), _uuid(conversation_id)
        if not tenant_uuid or not conversation_uuid:
            return None
        conversation = db.query(Conversation).filter(Conversation.id == conversation_uuid, Conversation.tenant_id == tenant_uuid).first()
        if not conversation:
            return None
        count = conversation.message_count or 0
        if not force and count < _settings.CONVERSATION_SUMMARY_TURN_INTERVAL:
            return None
        existing = db.query(ConversationSummary).filter(ConversationSummary.tenant_id == tenant_uuid, ConversationSummary.conversation_id == conversation_uuid, ConversationSummary.summary_type == "structured", ConversationSummary.source_message_count == count).first()
        if existing and existing.status == "ready":
            return existing
        summary_row = existing or ConversationSummary(tenant_id=tenant_uuid, conversation_id=conversation_uuid, summary_type="structured", summary="", source_message_count=count, status="pending", metadata_={})
        if not existing:
            db.add(summary_row)
        db.commit()
        turns = db.query(Message).filter(Message.tenant_id == tenant_uuid, Message.conversation_id == conversation_uuid).order_by(Message.sequence_number).all()
        transcript = "\n".join(f"{turn.speaker or turn.role}: {turn.content}" for turn in turns[-30:])
        payload = {"summary": transcript[-1800:], "pain_points": [], "budget_signals": [], "timeline": [], "stakeholders": [], "objections": [], "preferences": [], "competitors": []}
        if _settings.MISTRAL_API_KEY:
            prompt = "Return JSON only with summary, pain_points, budget_signals, timeline, stakeholders, objections, preferences, competitors. Use only evidence in these turns.\n" + transcript
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(f"{_settings.MISTRAL_API_BASE}/chat/completions", headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"}, json={"model": _settings.MISTRAL_CHAT_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "response_format": {"type": "json_object"}, "max_tokens": 700})
                response.raise_for_status()
            payload = json.loads(response.json()["choices"][0]["message"]["content"])
        summary_row.summary = str(payload.get("summary") or transcript[-1800:])
        summary_row.status = "ready"
        summary_row.metadata_ = {"structured": payload, "provider": "mistral" if _settings.MISTRAL_API_KEY else "deterministic-fallback"}
        conversation.summary = summary_row.summary
        conversation.analysis_status = "ready"
        conversation.last_analysis_at = datetime.utcnow()
        subject_type = "lead" if conversation.lead_id else "customer" if conversation.customer_id else "conversation"
        subject_id = str(conversation.lead_id or conversation.customer_id or conversation.id)
        enqueue_sync_event(
            db,
            tenant_id=tenant_uuid,
            event_type="conversation.summary.ready",
            aggregate_type="conversation_summary",
            aggregate_id=summary_row.id,
            idempotency_key=f"conversation-summary:{summary_row.id}:{count}",
            payload={
                "summary_id": str(summary_row.id),
                "conversation_id": str(conversation.id),
                "customer_id": str(conversation.customer_id) if conversation.customer_id else None,
                "lead_id": str(conversation.lead_id) if conversation.lead_id else None,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "summary": summary_row.summary,
                "structured": payload,
            },
        )
        # The SQL summary and its outbox event commit together. External stores are retried later.
        db.commit()
        db.refresh(summary_row)
        return summary_row
    except Exception as exc:
        db.rollback()
        # Turns are already safely committed; callers may retry this summary later.
        return None
    finally:
        db.close()





