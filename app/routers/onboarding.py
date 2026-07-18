"""Tenant onboarding profile API. Company-level setup details only.

Tenant scope always comes from the JWT (see Fix 3), never from the request
body — there is nothing here for a caller to spoof, so there is no
mismatch-rejection dance to run, unlike the endpoints in the stabilization pass
that had a pre-existing tenant_id-in-body contract to keep working.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id
from app.models.onboarding_profile import OnboardingProfile
from app.repositories.onboarding_profile import OnboardingProfileRepository

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

_REQUIRED_FIELDS = ("company_name", "timezone")


class OnboardingProfileCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    timezone: str = Field(..., min_length=1, max_length=64)
    country_region: str | None = Field(None, max_length=120)


class OnboardingProfileUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    timezone: str | None = Field(None, min_length=1, max_length=64)
    country_region: str | None = Field(None, max_length=120)


class OnboardingProfileResponse(BaseModel):
    id: str
    tenant_id: str
    company_name: str
    website: str | None
    timezone: str
    country_region: str | None


def _response(profile: OnboardingProfile) -> OnboardingProfileResponse:
    return OnboardingProfileResponse(
        id=str(profile.id),
        tenant_id=str(profile.tenant_id),
        company_name=profile.company_name,
        website=profile.website,
        timezone=profile.timezone,
        country_region=profile.country_region,
    )


@router.post("/profile", response_model=OnboardingProfileResponse, status_code=status.HTTP_201_CREATED)
def create_onboarding_profile(
    payload: OnboardingProfileCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    repo = OnboardingProfileRepository(db)
    if repo.get_by_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Onboarding profile already exists for this tenant; use PATCH to update it")
    profile = OnboardingProfile(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        company_name=payload.company_name,
        website=payload.website,
        timezone=payload.timezone,
        country_region=payload.country_region,
    )
    profile = repo.create(profile)
    return _response(profile)


@router.patch("/profile", response_model=OnboardingProfileResponse)
def update_onboarding_profile(
    payload: OnboardingProfileUpdate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    repo = OnboardingProfileRepository(db)
    profile = repo.get_by_tenant(tenant_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No onboarding profile exists yet for this tenant; POST one first")
    profile = repo.update(profile, **payload.model_dump())
    return _response(profile)


@router.get("/status")
def onboarding_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    repo = OnboardingProfileRepository(db)
    profile = repo.get_by_tenant(tenant_id)
    if not profile:
        return {"tenant_id": tenant_id, "profile_exists": False, "complete": False, "missing_fields": list(_REQUIRED_FIELDS)}
    missing = [field for field in _REQUIRED_FIELDS if not getattr(profile, field)]
    return {"tenant_id": tenant_id, "profile_exists": True, "complete": not missing, "missing_fields": missing}
