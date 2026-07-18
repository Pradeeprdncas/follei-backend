"""Repository for a tenant's selected onboarding contact channels."""
import uuid

from sqlalchemy.orm import Session

from app.models.onboarding_contact_channel import OnboardingContactChannel


class OnboardingContactChannelRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_tenant(self, tenant_id) -> list[str]:
        rows = self.db.query(OnboardingContactChannel).filter(OnboardingContactChannel.tenant_id == tenant_id).all()
        return [row.channel for row in rows]

    def replace_for_tenant(self, tenant_id, channels: list[str]) -> list[str]:
        """Set the tenant's channel selection to exactly `channels` (dedup, preserve order)."""
        self.db.query(OnboardingContactChannel).filter(OnboardingContactChannel.tenant_id == tenant_id).delete()
        seen: list[str] = []
        for channel in channels:
            if channel in seen:
                continue
            seen.append(channel)
            self.db.add(OnboardingContactChannel(id=uuid.uuid4(), tenant_id=tenant_id, channel=channel))
        self.db.commit()
        return seen
