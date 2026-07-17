"""CampaignMessage repository — owns all message-level database interactions."""
from uuid import UUID
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.campaigns import CampaignMessage, DeliveryStatus


class CampaignMessageRepository(BaseRepository[CampaignMessage]):
    def __init__(self, db: Session):
        super().__init__(db, CampaignMessage)

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    # ── Query ─────────────────────────────────────────────────────────

    def get_by_campaign(self, campaign_id: Any) -> list[CampaignMessage]:
        cid = self._uuid(campaign_id)
        return self.db.query(CampaignMessage).filter(
            CampaignMessage.campaign_id == cid
        ).all()

    def get_by_campaign_paginated(self, campaign_id: Any, page: int = 1,
                                  page_size: int = 20) -> tuple[list[CampaignMessage], int]:
        cid = self._uuid(campaign_id)
        q = self.db.query(CampaignMessage).filter(CampaignMessage.campaign_id == cid)
        total = q.count()
        messages = q.offset((page - 1) * page_size).limit(page_size).all()
        return messages, total

    def get_by_lead(self, lead_id: Any) -> list[CampaignMessage]:
        lid = self._uuid(lead_id)
        return self.db.query(CampaignMessage).filter(
            CampaignMessage.lead_id == lid
        ).all()

    def count_by_status(self, campaign_id: Any, status: DeliveryStatus) -> int:
        cid = self._uuid(campaign_id)
        return self.db.query(CampaignMessage).filter(
            CampaignMessage.campaign_id == cid,
            CampaignMessage.status == status,
        ).count()

    def get_statistics_by_campaign(self, campaign_id: Any) -> dict[str, int]:
        cid = self._uuid(campaign_id)
        from sqlalchemy import func
        rows = self.db.query(
            CampaignMessage.status,
            func.count(CampaignMessage.id).label("count")
        ).filter(CampaignMessage.campaign_id == cid).group_by(CampaignMessage.status).all()
        stats = {"total": 0}
        for status_enum, count in rows:
            key = status_enum.value if hasattr(status_enum, 'value') else str(status_enum)
            stats[key] = count
            stats["total"] += count
        return stats

    def get_lead_ids_by_campaign(self, campaign_id: Any) -> list[str]:
        cid = self._uuid(campaign_id)
        rows = self.db.query(CampaignMessage.lead_id).filter(
            CampaignMessage.campaign_id == cid
        ).all()
        return [str(r[0]) for r in rows]

    # ── Status updates ────────────────────────────────────────────────

    def update_status(self, message_id: Any, status: DeliveryStatus,
                      provider_id: str | None = None, error: str | None = None) -> None:
        pk = self._uuid(message_id)
        updates = {"status": status}
        if provider_id:
            updates["provider_message_id"] = provider_id
        if error:
            updates["error_message"] = error
        self.db.query(CampaignMessage).filter(CampaignMessage.id == pk).update(updates)
        self.db.commit()

    def bulk_insert(self, messages: list[CampaignMessage]) -> None:
        for msg in messages:
            self.db.add(msg)
        self.db.commit()

    def bulk_update_status(self, message_ids: list[Any], status: DeliveryStatus) -> None:
        pks = [self._uuid(mid) for mid in message_ids]
        self.db.query(CampaignMessage).filter(
            CampaignMessage.id.in_(pks)
        ).update({"status": status}, synchronize_session=False)
        self.db.commit()

    # ── Tracking ──────────────────────────────────────────────────────

    def track_open(self, message_id: Any) -> CampaignMessage | None:
        pk = self._uuid(message_id)
        msg = self.db.get(CampaignMessage, pk)
        if msg and msg.status.value in ("pending", "queued", "sent", "delivered"):
            msg.status = DeliveryStatus.OPENED
            msg.opened_at = datetime.utcnow()
            self.db.commit()
        return msg

    def track_click(self, message_id: Any) -> CampaignMessage | None:
        pk = self._uuid(message_id)
        msg = self.db.get(CampaignMessage, pk)
        if msg:
            msg.status = DeliveryStatus.CLICKED
            msg.clicked_at = datetime.utcnow()
            self.db.commit()
        return msg

    def track_delivery(self, message_id: Any, status: DeliveryStatus,
                       provider_id: str | None = None, error: str | None = None) -> CampaignMessage | None:
        pk = self._uuid(message_id)
        msg = self.db.get(CampaignMessage, pk)
        if msg:
            msg.status = status
            if provider_id:
                msg.provider_message_id = provider_id
            if error:
                msg.error_message = error
            if status == DeliveryStatus.DELIVERED:
                msg.delivered_at = datetime.utcnow()
            elif status == DeliveryStatus.FAILED:
                msg.failed_at = datetime.utcnow()
            elif status == DeliveryStatus.BOUNCED:
                msg.failed_at = datetime.utcnow()
            self.db.commit()
        return msg

    def track_reply(self, message_id: Any) -> CampaignMessage | None:
        pk = self._uuid(message_id)
        msg = self.db.get(CampaignMessage, pk)
        if msg:
            msg.status = DeliveryStatus.REPLIED
            msg.replied_at = datetime.utcnow()
            self.db.commit()
        return msg

    def track_bounce(self, message_id: Any, error: str | None = None) -> CampaignMessage | None:
        return self.track_delivery(message_id, DeliveryStatus.BOUNCED, error=error)
