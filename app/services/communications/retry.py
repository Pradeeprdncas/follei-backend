"""RetryEngine — configurable retry policy with exponential backoff."""
from datetime import datetime, timedelta
from typing import Any
from loguru import logger

from app.repositories.outbox import OutboxRepository
from app.services.communications.exceptions import RetryExhaustedError


DEFAULT_RETRY_POLICY = {
    "max_retries": 3,
    "base_delay_seconds": 60,
    "backoff_factor": 4,
    "max_delay_seconds": 3600,
}


class RetryEngine:
    """Manages retry scheduling with exponential backoff + dead letter queue."""

    def __init__(self, outbox_repo: OutboxRepository,
                 policy: dict | None = None):
        self.repo = outbox_repo
        self.policy = {**DEFAULT_RETRY_POLICY, **(policy or {})}

    def schedule_retry(self, outbox_id: str, error: str = "") -> bool:
        """Schedule a retry or move to dead letter queue if exhausted."""
        msg = self.repo.get_by_id(outbox_id)
        if not msg:
            return False

        retry_count = (msg.retry_count or 0) + 1
        max_retries = msg.max_retries or self.policy["max_retries"]

        if retry_count > max_retries:
            self.repo.mark_dead_letter(outbox_id, error)
            self._mark_linked_dead_letter(msg, error)
            logger.warning(f"Outbox {outbox_id} moved to DLQ after {retry_count} retries")
            return False

        delay = self._backoff_delay(retry_count)
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)
        self.repo.schedule_retry(outbox_id, scheduled_at=scheduled_at, error=error)
        logger.info(f"Outbox {outbox_id} retry #{retry_count} scheduled in {delay}s")
        return True

    def _mark_linked_dead_letter(self, msg, error: str) -> None:
        """Finalize campaign/conversation state when delivery retries are exhausted."""
        from app.models.campaigns import Campaign, CampaignMessage, CampaignStatus, DeliveryStatus
        from app.models.conversations.conversation import MessageDeliveryStatus

        if msg.campaign_message_id:
            campaign_message = self.repo.db.get(CampaignMessage, msg.campaign_message_id)
            if campaign_message and campaign_message.status != DeliveryStatus.FAILED:
                campaign_message.status = DeliveryStatus.FAILED
                campaign_message.failed_at = datetime.utcnow()
                campaign_message.error_message = error[:2000]
                campaign = self.repo.db.get(Campaign, campaign_message.campaign_id)
                if campaign:
                    campaign.failed_count = (campaign.failed_count or 0) + 1
                    remaining = self.repo.db.query(CampaignMessage).filter(
                        CampaignMessage.campaign_id == campaign.id,
                        CampaignMessage.status.in_((DeliveryStatus.PENDING, DeliveryStatus.QUEUED)),
                    ).count()
                    if remaining == 0:
                        campaign.status = CampaignStatus.COMPLETED
                        campaign.processing_started_at = None
                        campaign.end_date = datetime.utcnow()
        if msg.conversation_message_id:
            self.repo.db.add(MessageDeliveryStatus(
                tenant_id=msg.tenant_id,
                message_id=msg.conversation_message_id,
                status="failed",
                provider=msg.provider,
                metadata_={"error": error[:2000]},
            ))
        self.repo.db.commit()

    def get_due_retries(self, batch_size: int = 50) -> list[str]:
        """Get outbox messages due for retry."""
        return self.repo.get_due_retries(batch_size=batch_size)

    def _backoff_delay(self, retry_count: int) -> int:
        delay = self.policy["base_delay_seconds"] * (self.policy["backoff_factor"] ** (retry_count - 1))
        return min(int(delay), self.policy["max_delay_seconds"])
