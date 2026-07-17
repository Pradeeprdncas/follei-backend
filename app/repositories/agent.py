"""Agent repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.agents.agent import Agent


class AgentRepository(BaseRepository[Agent]):
    def __init__(self, db: Session):
        super().__init__(db, Agent)

    def get_by_tenant(self, tenant_id: Any) -> list[Agent]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Agent).filter(
            Agent.tenant_id == tid
        ).all()

    def get_active_by_tenant(self, tenant_id: Any) -> list[Agent]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Agent).filter(
            Agent.tenant_id == tid,
            Agent.is_active == True,
        ).all()
