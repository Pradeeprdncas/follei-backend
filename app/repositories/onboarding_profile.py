"""Repository for the per-tenant onboarding profile."""
from sqlalchemy.orm import Session

from app.models.onboarding_profile import OnboardingProfile


class OnboardingProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_tenant(self, tenant_id) -> OnboardingProfile | None:
        return self.db.query(OnboardingProfile).filter(OnboardingProfile.tenant_id == tenant_id).first()

    def create(self, profile: OnboardingProfile) -> OnboardingProfile:
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update(self, profile: OnboardingProfile, **fields) -> OnboardingProfile:
        for key, value in fields.items():
            if value is not None:
                setattr(profile, key, value)
        self.db.commit()
        self.db.refresh(profile)
        return profile
