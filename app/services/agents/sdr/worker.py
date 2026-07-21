"""SDR worker: qualify and nurture a lead over one conversation turn.

Built on the same foundation as the Support worker
(app/services/agents/support/worker.py): it does a cheap rule-based intent
pass first, then reuses the already-proven chat_pipeline() for a grounded,
cited answer rather than making its own retrieval+LLM calls. On top of that it
adds the SDR-specific behaviours System 5 calls for:

  * Lead qualification — every turn is scored by the Lead Intelligence Engine
    (LeadIntelligenceService) and folded onto the Lead via apply_lead_qualification().
  * Discovery — the grounded answer is followed by the engine's next-best-action
    nudge so the SDR keeps the conversation moving toward qualification.
  * Meeting booking — an explicit meeting request is recorded as a durable
    ConversationAction and acknowledged.
  * Handoff — once a lead crosses the qualification threshold, the result flags
    it ready for the Sales Executive worker (the orchestrator acts on this).

The reply is composed as [grounded answer] + [SDR nudge] rather than by
swapping chat_pipeline()'s system prompt, so chat_pipeline()'s audited grounding
behaviour is preserved unchanged.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from loguru import logger

from app.services.agents.sdr.intent import classify_sdr_intent
from app.services.agents.actions import record_action, apply_lead_qualification
from app.services.rag.pipelines.chat import chat_pipeline
from app.analysis.services.lead_scoring_service import LeadScoringService

MEETING_ACK = "I'd be glad to set that up. What day and time work best for you, and I'll get it on the calendar?"
_SUB_SCORE_KEYS = (
    "icp_score", "intent_score", "engagement_score",
    "qualification_score", "buying_signal_score", "relationship_score",
)


async def handle_sdr_turn(
    db: Session,
    *,
    tenant_id: str,
    text: str,
    lead_id: str | None = None,
    session_id: str | None = None,
    channel: str = "voice",
    response_language: str | None = None,
) -> dict[str, Any]:
    """Process one inbound lead message as an SDR.

    Returns what happened: the reply to send, the six lead-intelligence
    sub-scores, the applied qualification, any durable actions taken, and
    whether the lead is now ready to hand off to Sales.
    """
    intent = classify_sdr_intent(text)

    # Grounded, cited answer via the shared pipeline (same as the Support worker).
    result = await chat_pipeline(question=text, tenant_id=tenant_id, session_id=session_id,
                                 response_language=response_language)
    conversation_id = result.get("conversation_id")
    grounded_answer = result.get("answer") or ""

    # Score this turn with the full Lead Intelligence Engine and fold it onto the lead.
    scores = LeadScoringService.score(text)
    sub_scores = {key: scores.get(key) for key in _SUB_SCORE_KEYS}
    lead_score = scores.get("lead_score")
    qualification = apply_lead_qualification(db, lead_id=lead_id, scores=scores)

    actions: list[str] = []
    if intent == "wants_meeting":
        record_action(
            db, tenant_id=tenant_id, conversation_id=conversation_id,
            action_type="meeting_booked",
            payload={"lead_id": lead_id, "requested_via": channel, "request_text": text},
        )
        actions.append("meeting_booked")
        reply = MEETING_ACK
    else:
        # Discovery: pair the grounded answer with the engine's next-best-action.
        next_action = LeadScoringService.generate_next_action(
            float(lead_score or 0.0), scores=scores, text=text,
        )
        reply = " ".join(part for part in (grounded_answer, next_action) if part).strip()

    handoff_to_sales = bool(qualification and qualification.get("qualified"))

    logger.info(
        f"SDR worker: tenant={tenant_id} conversation={conversation_id} intent={intent} "
        f"lead_score={lead_score} handoff_to_sales={handoff_to_sales} actions={actions}"
    )
    return {
        "worker": "sdr",
        "conversation_id": conversation_id,
        "intent": intent,
        "reply": reply,
        "grounded_answer": grounded_answer,
        "scores": sub_scores,
        "lead_score": lead_score,
        "qualification": qualification,
        "actions": actions,
        "handoff_to_sales": handoff_to_sales,
        "confidence": result.get("confidence"),
        "citations": result.get("citations"),
    }
