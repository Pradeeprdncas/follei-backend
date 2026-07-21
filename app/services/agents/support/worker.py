"""Support worker: one inbound customer message -> a grounded reply or a
human handoff. Built on top of the existing, already-fixed pipeline —
chat_pipeline() already calls build_agent_context() (Fix 2) and already
returns `conflicts`/`confidence`/`supported`, so this worker does not make a
second, duplicate call to /knowledge/orchestrator/context; it reads those
fields off chat_pipeline()'s result instead.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.services.agents.support.intent import classify_intent
from app.services.knowledge.conversation_memory import persist_chat_turn
from app.services.rag.pipelines.chat import chat_pipeline
from app.models.conversations.conversation import Conversation
from loguru import logger

_settings = get_settings()

ESCALATION_ACK = "Thanks for reaching out — I've flagged this for a member of our support team, who will follow up with you shortly."

# Deliberately stricter than the general chat MIN_CONFIDENCE: a support ticket
# is a worse place to guess than an open chat widget.
SUPPORT_MIN_CONFIDENCE = max(_settings.MIN_CONFIDENCE, 0.6)


def _mark_needs_human(db: Session, conversation_id: str, *, reason: str, detail: dict[str, Any] | None = None) -> None:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        return
    conversation.status = "needs_human"
    metadata = dict(conversation.metadata_ or {})
    metadata["escalation"] = {"reason": reason, "detail": detail or {}, "triggered_at": datetime.utcnow().isoformat()}
    conversation.metadata_ = metadata
    db.commit()


async def handle_inbound_message(
    db: Session, *, tenant_id: str, text: str, session_id: str | None = None,
    channel: str = "email", response_language: str | None = None,
) -> dict[str, Any]:
    """Process one inbound support message end to end.

    Returns a dict describing what happened: whether the customer gets an
    auto-reply or a handoff acknowledgement, why, and the conversation id.
    """
    intent = classify_intent(text)

    if intent == "escalation_requested":
        # Explicit human request: don't spend a retrieval+LLM call guessing an
        # answer the customer didn't ask for. Persist the turn via the same
        # shared primitive chat_pipeline() uses, with a canned handoff reply.
        conversation = persist_chat_turn(
            db, tenant_id=tenant_id, session_id=session_id, question=text,
            answer=ESCALATION_ACK, citations=[], confidence=0.0, supported=False,
            reason="Customer explicitly requested a human.", channel=channel,
        )
        _mark_needs_human(db, str(conversation.id), reason="explicit_human_request")
        logger.info(f"Support worker: tenant={tenant_id} conversation={conversation.id} escalated (explicit request)")
        return {
            "conversation_id": str(conversation.id),
            "intent": intent,
            "escalated": True,
            "escalation_reason": "explicit_human_request",
            "reply": ESCALATION_ACK,
        }

    result = await chat_pipeline(
        question=text, tenant_id=tenant_id, session_id=session_id,
        response_language=response_language,
    )
    conversation_id = result.get("conversation_id")

    escalation_reason = None
    if result.get("conflicts"):
        escalation_reason = "conflicting_approved_facts"
    elif not result.get("supported", False):
        escalation_reason = "unsupported_answer"
    elif result.get("confidence", 0.0) < SUPPORT_MIN_CONFIDENCE:
        escalation_reason = "low_confidence"

    if escalation_reason and conversation_id:
        _mark_needs_human(db, conversation_id, reason=escalation_reason, detail={
            "confidence": result.get("confidence"),
            "supported": result.get("supported"),
            "conflicts": result.get("conflicts"),
        })
        logger.info(f"Support worker: tenant={tenant_id} conversation={conversation_id} escalated ({escalation_reason})")
        return {
            "conversation_id": conversation_id,
            "intent": intent,
            "escalated": True,
            "escalation_reason": escalation_reason,
            "reply": ESCALATION_ACK,
        }

    return {
        "conversation_id": conversation_id,
        "intent": intent,
        "escalated": False,
        "escalation_reason": None,
        "reply": result.get("answer"),
        "confidence": result.get("confidence"),
        "citations": result.get("citations"),
    }
