"""Lead repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.leads.lead import Lead


class LeadRepository(BaseRepository[Lead]):
    def __init__(self, db: Session):
        super().__init__(db, Lead)

    def get_by_tenant(self, tenant_id: Any) -> list[Lead]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Lead).filter(
            Lead.tenant_id == tid
        ).order_by(Lead.created_at.desc()).all()

    def get_by_email(self, tenant_id: Any, email: str) -> Lead | None:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Lead).filter(
            Lead.tenant_id == tid,
            Lead.email == email,
        ).first()

    def update_score(self, lead_id: Any, score: int, temperature: str) -> None:
        pk = self._to_uuid(lead_id)
        self.db.query(Lead).filter(Lead.id == pk).update({
            "revenue_score": score,
            "current_temperature": temperature,
        })
        self.db.commit()
