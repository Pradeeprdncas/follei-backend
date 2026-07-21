"""Sales Executive worker: progress a qualified lead toward a closed deal.

Same foundation as the Support and SDR workers (cheap intent pass, then the
proven chat_pipeline() for a grounded, cited answer). On top of that it adds
the Sales-specific System 5 behaviours:

  * Product explanation — the grounded answer from chat_pipeline() is the
    product/knowledge explanation, cited from approved business facts.
  * Objection handling — an objection is answered from grounded context, framed
    as a reassurance rather than a bare fact dump.
  * Proposal generation — a proposal request produces a structured proposal
    (recorded as a durable ConversationAction) and an acknowledgement.
  * Deal progression — a clear closing signal advances Lead.status/temperature
    and records a deal_stage_change action.

Like the SDR worker, the reply is composed from chat_pipeline()'s grounded
answer plus Sales framing rather than by swapping its system prompt, so the
audited grounding path is preserved unchanged.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from loguru import logger

from app.services.agents.sales.intent import classify_sales_intent
from app.services.agents.actions import record_action
from app.services.rag.pipelines.chat import chat_pipeline
from app.analysis.services.lead_scoring_service import LeadScoringService
from app.models.leads.lead import Lead

OBJECTION_PREFIX = "I completely understand the concern."
PROPOSAL_ACK = "I've put together a proposal covering scope, pricing, and next steps — I'll send it over for your review."
CLOSING_ACK = "That's great to hear. I'll get the paperwork moving so we can get you started right away."


def _build_proposal(lead: Lead | None, scores: dict[str, Any], grounded_answer: str) -> dict[str, Any]:
    """A structured proposal derived from what the pipeline already knows.

    Deliberately not a document-generation engine: it captures the fields a
    proposal needs (recommendation, temperature, grounded summary) so the
    action ledger has something concrete, leaving formatted-document output to
    a later pass.
    """
    lead_score = float(scores.get("lead_score") or 0.0)
    return {
        "lead_id": str(lead.id) if lead else None,
        "company": lead.company if lead else None,
        "lead_score": lead_score,
        "temperature": LeadScoringService.categorize_lead(lead_score),
        "recommendation": LeadScoringService.generate_next_action(lead_score, scores=scores),
        "summary": grounded_answer,
        "generated_at": datetime.utcnow().isoformat(),
    }


async def handle_sales_turn(
    db: Session,
    *,
    tenant_id: str,
    text: str,
    lead_id: str | None = None,
    session_id: str | None = None,
    channel: str = "voice",
    response_language: str | None = None,
) -> dict[str, Any]:
    """Process one inbound message as a Sales Executive.

    Returns the reply, the deal-stage outcome, any durable actions taken
    (proposal_generated / deal_stage_change), and the latest scores.
    """
    intent = classify_sales_intent(text)

    result = await chat_pipeline(question=text, tenant_id=tenant_id, session_id=session_id,
                                 response_language=response_language, lead_id=lead_id)
    conversation_id = result.get("conversation_id")
    grounded_answer = result.get("answer") or ""

    scores = LeadScoringService.score(text)
    lead_score = scores.get("lead_score")
    lead = db.query(Lead).filter(Lead.id == lead_id).first() if lead_id else None

    actions: list[str] = []
    proposal: dict[str, Any] | None = None
    deal_stage: str | None = None

    if intent == "objection":
        reply = " ".join(part for part in (OBJECTION_PREFIX, grounded_answer) if part).strip()

    elif intent == "wants_proposal":
        proposal = _build_proposal(lead, scores, grounded_answer)
        record_action(
            db, tenant_id=tenant_id, conversation_id=conversation_id,
            action_type="proposal_generated", payload=proposal, commit=False,
        )
        actions.append("proposal_generated")
        if lead and lead.status in (None, "new", "contacted", "qualified"):
            lead.status = "proposal"
            deal_stage = "proposal"
        db.commit()
        reply = PROPOSAL_ACK

    elif intent == "closing":
        if lead:
            lead.status = "converted"
            lead.current_temperature = "customer"
            lead.last_analysis_at = datetime.utcnow()
            deal_stage = "closed_won"
        record_action(
            db, tenant_id=tenant_id, conversation_id=conversation_id,
            action_type="deal_stage_change",
            payload={"lead_id": lead_id, "stage": "closed_won", "trigger_text": text},
            commit=False,
        )
        actions.append("deal_stage_change")
        db.commit()
        reply = CLOSING_ACK

    else:  # product_discussion
        reply = grounded_answer or "Happy to walk you through how it works — what would you like to dig into?"

    logger.info(
        f"Sales worker: tenant={tenant_id} conversation={conversation_id} intent={intent} "
        f"lead_score={lead_score} deal_stage={deal_stage} actions={actions}"
    )
    return {
        "worker": "sales",
        "conversation_id": conversation_id,
        "intent": intent,
        "reply": reply,
        "grounded_answer": grounded_answer,
        "lead_score": lead_score,
        "deal_stage": deal_stage,
        "proposal": proposal,
        "actions": actions,
        "confidence": result.get("confidence"),
        "citations": result.get("citations"),
    }
