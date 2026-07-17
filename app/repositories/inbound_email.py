"""InboundEmail repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.campaigns import InboundEmail


class InboundEmailRepository(BaseRepository[InboundEmail]):
    def __init__(self, db: Session):
        super().__init__(db, InboundEmail)

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    def get_by_tenant(self, tenant_id: Any) -> list[InboundEmail]:
        tid = self._uuid(tenant_id)
        return self.db.query(InboundEmail).filter(
            InboundEmail.tenant_id == tid
        ).order_by(InboundEmail.received_at.desc()).all()

    def get_by_campaign(self, campaign_id: Any) -> list[InboundEmail]:
        cid = self._uuid(campaign_id)
        return self.db.query(InboundEmail).filter(
            InboundEmail.campaign_id == cid
        ).order_by(InboundEmail.received_at.desc()).all()

    def get_by_lead(self, lead_id: Any) -> list[InboundEmail]:
        lid = self._uuid(lead_id)
        return self.db.query(InboundEmail).filter(
            InboundEmail.lead_id == lid
        ).order_by(InboundEmail.received_at.desc()).all()
