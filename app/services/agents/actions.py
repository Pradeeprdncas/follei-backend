"""Shared side-effect helpers for AI workforce workers (SDR, Sales, ...).

Two durable side effects every revenue-facing worker needs, kept in one place
so SDR and Sales record them identically:

  * record_action() writes a ConversationAction row. That model already exists
    (app/models/conversations/conversation.py) but had zero writers until now —
    it's the natural, migration-free ledger for worker actions like
    meeting_booked / proposal_generated / deal_stage_change.
  * apply_lead_qualification() folds a LeadIntelligenceService score dict onto
    the Lead row (current_score / current_temperature / status), so a lead's
    latest qualification is readable straight off the Lead without replaying
    its conversation analyses. This complements app/workers/lead_scoring_worker.py
    (which reacts to Kafka analysis-completed events); a worker turn updates the
    lead synchronously in the same request instead of waiting on the event loop.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from loguru import logger

from app.models.conversations.conversation import ConversationAction
from app.models.leads.lead import Lead
from app.analysis.services.lead_intelligence_service import LeadIntelligenceService

# A lead at or above this composite score is "qualified" enough for an SDR to
# hand off to Sales. Kept here so SDR (which gates the handoff) and any future
# reader agree on one threshold.
SDR_QUALIFICATION_THRESHOLD = 40.0


def record_action(
    db: Session,
    *,
    tenant_id: str | UUID,
    conversation_id: str | UUID | None,
    action_type: str,
    payload: dict[str, Any] | None = None,
    status: str = "completed",
    commit: bool = True,
) -> ConversationAction | None:
    """Append a durable ConversationAction. No-op (returns None) without a conversation."""
    if not conversation_id:
        return None
    action = ConversationAction(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        action_type=action_type,
        payload=payload or {},
        status=status,
    )
    db.add(action)
    if commit:
        db.commit()
    return action


def apply_lead_qualification(
    db: Session,
    *,
    lead_id: str | UUID | None,
    scores: dict[str, Any],
    commit: bool = True,
) -> dict[str, Any] | None:
    """Fold a LeadIntelligenceService.score() dict onto the Lead row.

    Returns a small summary ({lead_score, temperature, qualified, status}) or
    None when there is no lead to update. Status is only advanced, never
    regressed: a lead already 'converted'/'customer' is left alone.
    """
    if not lead_id:
        return None
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return None

    lead_score = float(scores.get("lead_score") or 0.0)
    qualification_score = float(scores.get("qualification_score") or 0.0)
    temperature = LeadIntelligenceService.categorize_score(lead_score)
    qualified = lead_score >= SDR_QUALIFICATION_THRESHOLD

    lead.current_score = lead_score
    lead.current_temperature = temperature
    lead.last_analysis_at = datetime.utcnow()
    conversion = scores.get("conversion_probability")
    if conversion is not None:
        lead.analysis_confidence = float(conversion)

    # Only ever advance status forward through the qualification funnel.
    if lead.status in (None, "new", "contacted") and qualified:
        lead.status = "qualified"
    elif lead.status in (None, "new") and not qualified:
        lead.status = "contacted"

    if commit:
        db.commit()

    logger.info(
        f"Lead {lead.id} qualification applied: score={lead_score:.1f} "
        f"temperature={temperature} status={lead.status} qualified={qualified}"
    )
    return {
        "lead_score": lead_score,
        "qualification_score": qualification_score,
        "temperature": temperature,
        "qualified": qualified,
        "status": lead.status,
    }
