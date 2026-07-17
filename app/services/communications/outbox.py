"""OutboxService — enqueue messages, commit, then async workers deliver."""
from uuid import uuid4
from datetime import datetime
from typing import Any
from loguru import logger

from app.models.campaigns import OutboxMessage
from app.repositories.outbox import OutboxRepository
from app.services.communications.protocols import CommunicationProvider, SendResult
from app.services.communications.router import CommunicationRouter
from app.services.communications.retry import RetryEngine
from app.services.communications.events import publish_event
from app.events.base import (
    EVENT_MESSAGE_QUEUED, EVENT_MESSAGE_SENT, EVENT_MESSAGE_FAILED,
)
from app.config.settings import get_settings


class OutboxService:
    """Writes outbox, commits, then sends (or delegates to workers)."""

    def __init__(self, outbox_repo: OutboxRepository,
                 router: CommunicationRouter | None = None,
                 retry_engine: RetryEngine | None = None):
        self.repo = outbox_repo
        self.router = router or CommunicationRouter()
        self.retry = retry_engine or RetryEngine(outbox_repo)
        self._settings = get_settings()

    def enqueue(self, tenant_id: str, channel: str, recipient: str,
                subject: str | None = None, body: str = "",
                html_body: str | None = None, sender_name: str | None = None,
                campaign_id: str | None = None,
                campaign_message_id: str | None = None,
                conversation_message_id: str | None = None,
                metadata: dict | None = None,
                priority: int = 0, max_retries: int = 3) -> OutboxMessage:
        msg = OutboxMessage(
            id=uuid4(),
            tenant_id=tenant_id, channel=channel,
            recipient=recipient, subject=subject, body=body,
            html_body=html_body, sender_name=sender_name,
            campaign_id=campaign_id,
            campaign_message_id=campaign_message_id,
            conversation_message_id=conversation_message_id,
            metadata_=metadata or {},
            status="pending", priority=priority,
            max_retries=max_retries,
        )
        self.repo.create(msg)
        publish_event(EVENT_MESSAGE_QUEUED, tenant_id, {
            "outbox_id": str(msg.id), "channel": channel, "recipient": recipient,
        })
        return msg

    async def send_sync(self, outbox_id: str) -> SendResult:
        """Send a single outbox message synchronously (used by workers)."""
        msg = self.repo.get_by_id(outbox_id)
        if not msg:
            return SendResult(success=False, error="Outbox message not found")

        self.repo.lock(outbox_id, worker_id="direct")
        try:
            result = await self.router.send(
                channel=msg.channel, recipient=msg.recipient,
                subject=msg.subject, body=msg.body,
                html_body=msg.html_body, sender_name=msg.sender_name,
                metadata=msg.metadata_,
            )
            if result.success:
                self.repo.mark_sent(outbox_id, result.provider_message_id,
                                     msg.channel, result.raw_response)
                publish_event(EVENT_MESSAGE_SENT, str(msg.tenant_id), {
                    "outbox_id": outbox_id,
                    "provider_message_id": result.provider_message_id,
                })
            else:
                self.repo.mark_failed(outbox_id, result.error or "Unknown error")
                publish_event(EVENT_MESSAGE_FAILED, str(msg.tenant_id), {
                    "outbox_id": outbox_id, "error": result.error,
                })
            return result
        except Exception as e:
            logger.error(f"Outbox send failed for {outbox_id}: {e}")
            self.repo.mark_failed(outbox_id, str(e))
            publish_event(EVENT_MESSAGE_FAILED, str(msg.tenant_id), {
                "outbox_id": outbox_id, "error": str(e),
            })
            return SendResult(success=False, error=str(e))

    def process_pending(self, batch_size: int = 50) -> list[str]:
        """Pick next pending batch, return their IDs for worker dispatch."""
        return self.repo.dequeue(batch_size=batch_size)
