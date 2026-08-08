"""UI-facing aggregate onboarding state and explicit confirmation APIs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.knowledge.ingestion import OnboardingConfirmation
from app.schemas.api_envelope import api_envelope
from app.services.knowledge.categories import MANDATORY_GROUPS, taxonomy_payload
from app.services.onboarding_state import build_onboarding_state


router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding-state"])


class ConfirmationRequest(BaseModel):
    requirement: str
    resolution: Literal["provided", "not_applicable", "confidential", "continue_without"]
    note: str | None = Field(default=None, max_length=1000)


@router.get("/taxonomy")
def get_taxonomy():
    return api_envelope({"categories": taxonomy_payload(), "mandatory_groups": MANDATORY_GROUPS})


@router.get("/state")
def get_state(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    return api_envelope(build_onboarding_state(db, uuid.UUID(tenant_id)))


@router.post("/confirmations", status_code=status.HTTP_200_OK)
def confirm_missing_requirement(
    payload: ConfirmationRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
    user_id: str = Depends(get_authenticated_user_id),
):
    if payload.requirement not in MANDATORY_GROUPS:
        raise HTTPException(status_code=422, detail="Unknown mandatory requirement")
    tenant_uuid = uuid.UUID(tenant_id)
    row = db.query(OnboardingConfirmation).filter(
        OnboardingConfirmation.tenant_id == tenant_uuid,
        OnboardingConfirmation.requirement_key == payload.requirement,
    ).first()
    if row is None:
        row = OnboardingConfirmation(tenant_id=tenant_uuid, requirement_key=payload.requirement)
        db.add(row)
    row.resolution = payload.resolution
    row.note = payload.note
    row.confirmed_by = uuid.UUID(user_id)
    row.confirmed_at = datetime.utcnow()
    db.commit()
    return api_envelope(build_onboarding_state(db, tenant_uuid))
