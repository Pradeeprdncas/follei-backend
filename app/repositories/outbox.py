"""OutboxRepository — owns all outbox_message table interactions."""
from uuid import UUID
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.campaigns import OutboxMessage


class OutboxRepository(BaseRepository[OutboxMessage]):
    def __init__(self, db: Session):
        super().__init__(db, OutboxMessage)

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    def create(self, msg: OutboxMessage) -> OutboxMessage:
        self.db.add(msg)
        self.db.commit()
        return msg

    def dequeue(self, batch_size: int = 50) -> list[str]:
        now = datetime.utcnow()
        rows = self.db.query(OutboxMessage).filter(
            OutboxMessage.status == "pending",
            (OutboxMessage.scheduled_at.is_(None)) | (OutboxMessage.scheduled_at <= now),
            OutboxMessage.locked_at.is_(None),
        ).order_by(OutboxMessage.priority.desc(), OutboxMessage.created_at.asc()).limit(batch_size).all()
        ids = []
        for row in rows:
            row.locked_at = datetime.utcnow()
            row.locked_by = "worker"
            row.status = "processing"
            ids.append(str(row.id))
        self.db.commit()
        return ids

    def dequeue_by_channel(self, channel: str, batch_size: int = 50) -> list[str]:
        now = datetime.utcnow()
        rows = self.db.query(OutboxMessage).filter(
            OutboxMessage.channel == channel,
            OutboxMessage.status == "pending",
            (OutboxMessage.scheduled_at.is_(None)) | (OutboxMessage.scheduled_at <= now),
            OutboxMessage.locked_at.is_(None),
        ).order_by(OutboxMessage.priority.desc(), OutboxMessage.created_at.asc()).limit(batch_size).all()
        ids = []
        for row in rows:
            row.locked_at = datetime.utcnow()
            row.locked_by = "worker"
            row.status = "processing"
            ids.append(str(row.id))
        self.db.commit()
        return ids

    def lock(self, outbox_id: Any, worker_id: str = "direct") -> bool:
        pk = self._uuid(outbox_id)
        row = self.db.get(OutboxMessage, pk)
        if row and row.locked_at is None:
            row.locked_at = datetime.utcnow()
            row.locked_by = worker_id
            row.status = "processing"
            self.db.commit()
            return True
        return False

    def mark_sent(self, outbox_id: Any, provider_message_id: str | None = None,
                  provider: str | None = None,
                  response: dict | None = None) -> None:
        pk = self._uuid(outbox_id)
        row = self.db.get(OutboxMessage, pk)
        if row:
            row.status = "sent"
            row.sent_at = datetime.utcnow()
            if provider_message_id:
                row.provider_message_id = provider_message_id
            if provider:
                row.provider = provider
            if response:
                row.provider_response = response
            self.db.commit()

    def mark_failed(self, outbox_id: Any, error: str) -> None:
        pk = self._uuid(outbox_id)
        row = self.db.get(OutboxMessage, pk)
        if row:
            row.status = "failed"
            row.last_error = error[:2000]
            row.retry_count = (row.retry_count or 0) + 1
            self.db.commit()

    def schedule_retry(self, outbox_id: Any, scheduled_at: datetime,
                       error: str = "") -> None:
        pk = self._uuid(outbox_id)
        row = self.db.get(OutboxMessage, pk)
        if row:
            row.status = "pending"
            row.scheduled_at = scheduled_at
            row.retry_count = (row.retry_count or 0) + 1
            row.last_error = error[:2000] if error else row.last_error
            row.locked_at = None
            row.locked_by = None
            self.db.commit()

    def mark_dead_letter(self, outbox_id: Any, error: str = "") -> None:
        pk = self._uuid(outbox_id)
        row = self.db.get(OutboxMessage, pk)
        if row:
            row.status = "dead_letter"
            row.last_error = error[:2000] if error else "Max retries exhausted"
            self.db.commit()

    def get_due_retries(self, batch_size: int = 50) -> list[str]:
        now = datetime.utcnow()
        rows = self.db.query(OutboxMessage).filter(
            OutboxMessage.status == "pending",
            OutboxMessage.scheduled_at.isnot(None),
            OutboxMessage.scheduled_at <= now,
            OutboxMessage.locked_at.is_(None),
        ).order_by(OutboxMessage.scheduled_at.asc()).limit(batch_size).all()
        ids = []
        for row in rows:
            row.locked_at = datetime.utcnow()
            row.locked_by = "retry-worker"
            ids.append(str(row.id))
        self.db.commit()
        return ids

    def purge_completed(self, before: datetime) -> int:
        deleted = self.db.query(OutboxMessage).filter(
            OutboxMessage.status.in_(["sent", "dead_letter"]),
            OutboxMessage.updated_at < before,
        ).delete(synchronize_session=False)
        self.db.commit()
        return deleted

    def get_by_campaign(self, campaign_id: Any) -> list[OutboxMessage]:
        cid = self._uuid(campaign_id)
        return self.db.query(OutboxMessage).filter(
            OutboxMessage.campaign_id == cid
        ).order_by(OutboxMessage.created_at.desc()).all()
