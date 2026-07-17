"""CampaignMetric repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.campaigns import CampaignMetric


class CampaignMetricRepository(BaseRepository[CampaignMetric]):
    def __init__(self, db: Session):
        super().__init__(db, CampaignMetric)

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    def get_by_campaign(self, campaign_id: Any) -> list[CampaignMetric]:
        cid = self._uuid(campaign_id)
        return self.db.query(CampaignMetric).filter(
            CampaignMetric.campaign_id == cid
        ).order_by(CampaignMetric.recorded_at.desc()).all()

    def get_by_campaign_and_type(self, campaign_id: Any, metric_type: str) -> list[CampaignMetric]:
        cid = self._uuid(campaign_id)
        return self.db.query(CampaignMetric).filter(
            CampaignMetric.campaign_id == cid,
            CampaignMetric.metric_type == metric_type,
        ).all()

    def get_by_type(self, metric_type: str) -> list[CampaignMetric]:
        return self.db.query(CampaignMetric).filter(
            CampaignMetric.metric_type == metric_type
        ).all()
