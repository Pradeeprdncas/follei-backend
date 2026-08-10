"""UI-facing aggregate onboarding state and explicit confirmation APIs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.knowledge.ingestion import OnboardingConfirmation
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.schemas.api_envelope import api_envelope
from app.services.knowledge.categories import (
    CATEGORY_DEFINITIONS,
    MANDATORY_GROUPS,
    canonical_taxonomy_key,
    fact_types_for_category,
    taxonomy_payload,
)
from app.services.onboarding_state import build_onboarding_state


router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding - knowledge review"])


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


@router.get("/categories/{key}/items")
def get_category_items(
    key: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Return one tenant's full extracted item records for paginated review."""
    try:
        canonical = canonical_taxonomy_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown onboarding category") from exc
    if canonical not in {definition.key for definition in CATEGORY_DEFINITIONS}:
        raise HTTPException(status_code=404, detail="Unknown onboarding category")

    tenant_uuid = uuid.UUID(tenant_id)
    query = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.tenant_id == tenant_uuid,
        BusinessFactDraft.fact_type.in_(fact_types_for_category(canonical)),
    )
    total = query.count()
    rows = (
        query.order_by(BusinessFactDraft.created_at.desc(), BusinessFactDraft.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    pages = (total + page_size - 1) // page_size if total else 0
    return api_envelope({
        "category": canonical,
        "items": [
            {
                "id": str(row.id),
                "fact_type": row.fact_type,
                "payload": row.payload,
                "citation": row.citation,
                "confidence": float(row.extraction_confidence) if row.extraction_confidence is not None else None,
                "review_status": row.item_review_status or "pending",
                "approval_status": row.approval_status,
                "reviewer": row.reviewer,
                "review_reason": row.review_reason,
                "created_at": row.created_at.isoformat(),
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": pages,
        },
    })


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
