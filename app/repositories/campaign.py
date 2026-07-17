"""Campaign repository — owns all campaign database interactions."""
from uuid import UUID
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.campaigns import Campaign, CampaignStatus


class CampaignRepository(BaseRepository[Campaign]):
    def __init__(self, db: Session):
        super().__init__(db, Campaign)

    # ── Helpers ───────────────────────────────────────────────────────

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    # ── Standard CRUD ─────────────────────────────────────────────────

    def create_campaign(self, campaign: Campaign) -> Campaign:
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def update_campaign(self, campaign: Campaign) -> Campaign:
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def delete_campaign(self, campaign_id: Any) -> bool:
        pk = self._uuid(campaign_id)
        campaign = self.db.get(Campaign, pk)
        if campaign:
            self.db.delete(campaign)
            self.db.commit()
            return True
        return False

    def get_campaign(self, campaign_id: Any) -> Campaign | None:
        pk = self._uuid(campaign_id)
        return self.db.get(Campaign, pk)

    def get_campaign_by_public_id(self, public_id: str) -> Campaign | None:
        return self.db.query(Campaign).filter(Campaign.public_id == public_id).first()

    # ── Listing with filters + pagination ────────────────────────────

    def list_campaigns(self, tenant_id: Any, status_filter: str | None = None,
                       type_filter: str | None = None, page: int = 1,
                       page_size: int = 20) -> tuple[list[Campaign], int]:
        tid = self._uuid(tenant_id)
        q = self.db.query(Campaign).filter(Campaign.tenant_id == tid)
        if status_filter:
            q = q.filter(Campaign.status == status_filter)
        if type_filter:
            q = q.filter(Campaign.type == type_filter)
        total = q.count()
        campaigns = q.order_by(Campaign.created_at.desc()).offset(
            (page - 1) * page_size).limit(page_size).all()
        return campaigns, total

    def get_by_tenant(self, tenant_id: Any) -> list[Campaign]:
        tid = self._uuid(tenant_id)
        return self.db.query(Campaign).filter(
            Campaign.tenant_id == tid
        ).order_by(Campaign.created_at.desc()).all()

    def get_by_status(self, tenant_id: Any, status: CampaignStatus) -> list[Campaign]:
        tid = self._uuid(tenant_id)
        return self.db.query(Campaign).filter(
            Campaign.tenant_id == tid,
            Campaign.status == status,
        ).all()

    def get_by_status_all(self, status: CampaignStatus) -> list[Campaign]:
        return self.db.query(Campaign).filter(Campaign.status == status).all()

    def get_scheduled_pending(self) -> list[Campaign]:
        now = datetime.utcnow()
        return self.db.query(Campaign).filter(
            Campaign.status == CampaignStatus.SCHEDULED,
            Campaign.start_date <= now,
        ).all()

    # ── Status transitions ────────────────────────────────────────────

    def mark_status(self, campaign_id: Any, status: CampaignStatus) -> None:
        pk = self._uuid(campaign_id)
        self.db.query(Campaign).filter(Campaign.id == pk).update({"status": status})
        self.db.commit()

    def set_processing(self, campaign_id: Any) -> bool:
        pk = self._uuid(campaign_id)
        now = datetime.utcnow()
        result = self.db.query(Campaign).filter(
            Campaign.id == pk,
            Campaign.processing_started_at.is_(None),
        ).update({"status": CampaignStatus.RUNNING, "processing_started_at": now, "start_date": now})
        self.db.commit()
        return result > 0

    def clear_processing(self, campaign_id: Any) -> None:
        pk = self._uuid(campaign_id)
        self.db.query(Campaign).filter(Campaign.id == pk).update(
            {"processing_started_at": None}
        )
        self.db.commit()

    # ── Statistics ────────────────────────────────────────────────────

    def increment_stat(self, campaign_id: Any, field: str, amount: int = 1) -> None:
        pk = self._uuid(campaign_id)
        campaign = self.db.get(Campaign, pk)
        if campaign:
            current = getattr(campaign, field, 0)
            setattr(campaign, field, current + amount)
            self.db.commit()

    def set_stats(self, campaign_id: Any, **stats) -> None:
        pk = self._uuid(campaign_id)
        self.db.query(Campaign).filter(Campaign.id == pk).update(stats)
        self.db.commit()
