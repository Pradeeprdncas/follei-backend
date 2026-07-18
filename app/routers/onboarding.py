"""Tenant onboarding profile API. Company-level setup details only.

Tenant scope always comes from the JWT (see Fix 3), never from the request
body — there is nothing here for a caller to spoof, so there is no
mismatch-rejection dance to run, unlike the endpoints in the stabilization pass
that had a pre-existing tenant_id-in-body contract to keep working.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.onboarding_profile import OnboardingProfile
from app.models.tenancy import User
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.repositories.onboarding_profile import OnboardingProfileRepository
from app.repositories.onboarding_contact_channel import OnboardingContactChannelRepository
from app.repositories.onboarding_goal import OnboardingGoalRepository
from app.repositories.user import UserRepository
from app.services.knowledge.document_status import list_document_statuses
from app.services.knowledge.extraction_review import group_extractions_by_category
from app.services.knowledge.memory_store import seed_onboarding_context

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

_REQUIRED_FIELDS = ("company_name", "timezone")

INDUSTRY_CHOICES = (
    "SaaS", "E-commerce", "Financial Services", "Healthcare", "Education",
    "Logistics & Transportation", "Manufacturing", "IT Services & Consulting",
    "Telecommunications", "Real Estate", "Media & Entertainment", "Other",
)
COMPANY_SIZE_CHOICES = ("1-10", "11-50", "51-200", "201-1000", "1000+")
CONTACT_CHANNEL_CHOICES = ("Email", "Phone", "SMS", "WhatsApp")
GOAL_CHOICES = (
    "Increase Revenue", "Find Upsell Opportunities", "Improve Customer Satisfaction",
    "Reduce Customer Churn", "Increase Product Adoption", "Track Customer Health",
    "Improve Conversion Rate", "Identify At-Risk Customers",
)
MAX_GOALS = 3


def _validate_contact_channels(value: list[str] | None) -> list[str] | None:
    if value is None:
        return value
    invalid = sorted(set(value) - set(CONTACT_CHANNEL_CHOICES))
    if invalid:
        raise ValueError(f"contact_channels contains invalid values {invalid}; allowed: {CONTACT_CHANNEL_CHOICES}")
    return value


def _validate_goals(value: list[str] | None) -> list[str] | None:
    if value is None:
        return value
    invalid = sorted(set(value) - set(GOAL_CHOICES))
    if invalid:
        raise ValueError(f"goals contains invalid values {invalid}; allowed: {GOAL_CHOICES}")
    if len(set(value)) > MAX_GOALS:
        raise ValueError(f"goals allows at most {MAX_GOALS} selections, got {len(set(value))}")
    return value


def _validate_industry(value: str | None) -> str | None:
    if value is not None and value not in INDUSTRY_CHOICES:
        raise ValueError(f"industry must be one of {INDUSTRY_CHOICES}")
    return value


def _validate_company_size(value: str | None) -> str | None:
    if value is not None and value not in COMPANY_SIZE_CHOICES:
        raise ValueError(f"company_size must be one of {COMPANY_SIZE_CHOICES}")
    return value


class OnboardingProfileCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    timezone: str = Field(..., min_length=1, max_length=64)
    country_region: str | None = Field(None, max_length=120)
    industry: str | None = Field(None)
    industry_other: str | None = Field(None, max_length=255)
    company_size: str | None = Field(None)
    contact_channels: list[str] | None = Field(None)
    goals: list[str] | None = Field(None)

    _check_industry = field_validator("industry")(_validate_industry)
    _check_company_size = field_validator("company_size")(_validate_company_size)
    _check_contact_channels = field_validator("contact_channels")(_validate_contact_channels)
    _check_goals = field_validator("goals")(_validate_goals)

    @model_validator(mode="after")
    def _industry_other_requires_other(self):
        if self.industry_other and self.industry != "Other":
            raise ValueError("industry_other is only valid when industry is 'Other'")
        return self


class OnboardingProfileUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    timezone: str | None = Field(None, min_length=1, max_length=64)
    country_region: str | None = Field(None, max_length=120)
    industry: str | None = Field(None)
    industry_other: str | None = Field(None, max_length=255)
    company_size: str | None = Field(None)
    contact_channels: list[str] | None = Field(None)
    goals: list[str] | None = Field(None)

    _check_industry = field_validator("industry")(_validate_industry)
    _check_company_size = field_validator("company_size")(_validate_company_size)
    _check_contact_channels = field_validator("contact_channels")(_validate_contact_channels)
    _check_goals = field_validator("goals")(_validate_goals)

    @model_validator(mode="after")
    def _industry_other_requires_other(self):
        if self.industry_other and self.industry not in (None, "Other"):
            raise ValueError("industry_other is only valid when industry is 'Other'")
        return self


class OnboardingProfileResponse(BaseModel):
    id: str
    tenant_id: str
    company_name: str
    website: str | None
    timezone: str
    country_region: str | None
    industry: str | None
    industry_other: str | None
    company_size: str | None
    contact_channels: list[str]
    goals: list[str]


def _response(profile: OnboardingProfile, contact_channels: list[str], goals: list[str]) -> OnboardingProfileResponse:
    return OnboardingProfileResponse(
        id=str(profile.id),
        tenant_id=str(profile.tenant_id),
        company_name=profile.company_name,
        website=profile.website,
        timezone=profile.timezone,
        country_region=profile.country_region,
        industry=profile.industry,
        industry_other=profile.industry_other,
        company_size=profile.company_size,
        contact_channels=contact_channels,
        goals=goals,
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
        industry=payload.industry,
        industry_other=payload.industry_other,
        company_size=payload.company_size,
    )
    profile = repo.create(profile)
    channels = OnboardingContactChannelRepository(db).replace_for_tenant(profile.tenant_id, payload.contact_channels or [])
    goals = OnboardingGoalRepository(db).replace_for_tenant(profile.tenant_id, payload.goals or [])
    return _response(profile, channels, goals)


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
    channel_repo = OnboardingContactChannelRepository(db)
    goal_repo = OnboardingGoalRepository(db)
    fields = payload.model_dump(exclude={"contact_channels", "goals"})
    profile = repo.update(profile, **fields)
    channels = channel_repo.replace_for_tenant(profile.tenant_id, payload.contact_channels) if payload.contact_channels is not None else channel_repo.get_for_tenant(profile.tenant_id)
    goals = goal_repo.replace_for_tenant(profile.tenant_id, payload.goals) if payload.goals is not None else goal_repo.get_for_tenant(profile.tenant_id)
    return _response(profile, channels, goals)


class OnboardingUserProfileUpdate(BaseModel):
    """Full name / job title / mobile number, plus the confirmation checkbox.

    Email is deliberately not editable here — changing the account's login
    email belongs in a dedicated, verified email-change flow, not a plain
    onboarding PATCH; out of scope for this pass.
    """

    full_name: str | None = Field(None, min_length=1, max_length=200)
    mobile_number: str | None = Field(None, max_length=32)
    job_title: str | None = Field(None, max_length=120)
    terms_accepted: bool | None = Field(None, description="Set true to record acceptance; false/omitted is a no-op, it does not revoke a prior acceptance.")


class OnboardingUserProfileResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    full_name: str | None
    mobile_number: str | None
    job_title: str | None
    terms_accepted: bool


def _user_response(user: User) -> OnboardingUserProfileResponse:
    return OnboardingUserProfileResponse(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        full_name=user.full_name,
        mobile_number=user.mobile_number,
        job_title=user.job_title,
        terms_accepted=user.onboarding_terms_accepted_at is not None,
    )


@router.patch("/user-profile", response_model=OnboardingUserProfileResponse)
def update_onboarding_user_profile(
    payload: OnboardingUserProfileUpdate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
    user_id: str = Depends(get_authenticated_user_id),
):
    repo = UserRepository(db)
    user = repo.get_by_id(user_id)
    if not user or str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this tenant")
    fields = payload.model_dump(exclude={"terms_accepted"}, exclude_none=True)
    if fields:
        repo.update(user_id, **fields)
    if payload.terms_accepted:
        repo.update(user_id, onboarding_terms_accepted_at=datetime.utcnow())
    db.refresh(user)
    return _user_response(user)


@router.get("/status")
def onboarding_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    repo = OnboardingProfileRepository(db)
    profile = repo.get_by_tenant(tenant_id)
    documents = list_document_statuses(db, tenant_id)
    if not profile:
        return {"tenant_id": tenant_id, "profile_exists": False, "complete": False, "missing_fields": list(_REQUIRED_FIELDS), "documents": documents}
    missing = [field for field in _REQUIRED_FIELDS if not getattr(profile, field)]
    return {"tenant_id": tenant_id, "profile_exists": True, "complete": not missing, "missing_fields": missing, "documents": documents}


@router.get("/extractions")
def onboarding_extractions(
    review_status: str = "draft",
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Extracted facts grouped into the review-tab categories shown in the UI."""
    return {"tenant_id": tenant_id, "categories": group_extractions_by_category(db, tenant_id, status=review_status)}


class ExtractionEditRequest(BaseModel):
    payload: dict = Field(..., description="Replacement payload for the draft fact. Edits the draft row; approval still happens via /knowledge/review/facts/{draft_id}/approve.")


@router.patch("/extractions/{draft_id}")
def edit_extraction_draft(
    draft_id: uuid.UUID,
    body: ExtractionEditRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    draft = db.query(BusinessFactDraft).filter(
        BusinessFactDraft.id == draft_id,
        BusinessFactDraft.tenant_id == uuid.UUID(tenant_id),
    ).with_for_update().first()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact draft not found for tenant")
    if draft.approval_status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Fact draft is already {draft.approval_status}; only drafts can be edited")
    draft.payload = body.payload
    db.commit()
    db.refresh(draft)
    return {
        "id": str(draft.id),
        "fact_type": draft.fact_type,
        "payload": draft.payload,
        "citation": draft.citation,
        "approval_status": draft.approval_status,
    }


@router.post("/complete")
def complete_onboarding(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Mark onboarding done and seed FerretDB's tenant-level context.

    Decision: does NOT require every extraction to be reviewed first. Required
    profile fields (company_name, timezone) are enough; remaining fact drafts
    stay reviewable later from the dashboard. Blocking workspace access on a
    full review pass would make onboarding an open-ended chore rather than a
    setup step, and document processing/extraction already has its own status
    visibility (GET /status, GET /extractions) for the user to catch up on
    later — there's no safety reason to gate access on it.
    """
    repo = OnboardingProfileRepository(db)
    profile = repo.get_by_tenant(tenant_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No onboarding profile exists yet for this tenant; POST one first")
    missing = [field for field in _REQUIRED_FIELDS if not getattr(profile, field)]
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Cannot complete onboarding, missing required fields: {missing}")

    already_completed = profile.completed_at is not None
    if not already_completed:
        profile.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(profile)

    goals = OnboardingGoalRepository(db).get_for_tenant(profile.tenant_id)
    channels = OnboardingContactChannelRepository(db).get_for_tenant(profile.tenant_id)
    seed_onboarding_context(tenant_id=str(profile.tenant_id), industry=profile.industry, goals=goals, contact_channels=channels)

    pending_review_count = sum(len(items) for items in group_extractions_by_category(db, tenant_id).values())
    return {
        "tenant_id": tenant_id,
        "completed_at": profile.completed_at,
        "already_completed": already_completed,
        "pending_review_count": pending_review_count,
    }
