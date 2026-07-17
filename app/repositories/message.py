"""Message repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.conversations.conversation import Message


class MessageRepository(BaseRepository[Message]):
    def __init__(self, db: Session):
        super().__init__(db, Message)

    def get_by_conversation(self, conversation_id: Any, limit: int = 100) -> list[Message]:
        cid = self._to_uuid(conversation_id)
        return self.db.query(Message).filter(
            Message.conversation_id == cid
        ).order_by(Message.created_at).limit(limit).all()

    def get_by_tenant(self, tenant_id: Any) -> list[Message]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Message).filter(
            Message.tenant_id == tid
        ).order_by(Message.created_at.desc()).all()
