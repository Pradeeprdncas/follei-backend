"""Conversation repository."""
from uuid import UUID
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.conversations.conversation import Conversation


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, db: Session):
        super().__init__(db, Conversation)

    def get_by_tenant(self, tenant_id: Any) -> list[Conversation]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Conversation).filter(
            Conversation.tenant_id == tid
        ).order_by(Conversation.created_at.desc()).all()

    def get_by_lead(self, lead_id: Any) -> list[Conversation]:
        lid = self._to_uuid(lead_id)
        return self.db.query(Conversation).filter(
            Conversation.lead_id == lid
        ).order_by(Conversation.created_at.desc()).all()

    def get_active_by_agent(self, agent_id: Any) -> list[Conversation]:
        aid = self._to_uuid(agent_id)
        return self.db.query(Conversation).filter(
            Conversation.agent_id == aid,
            Conversation.status == "active",
        ).all()
