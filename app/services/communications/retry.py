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
            logger.warning(f"Outbox {outbox_id} moved to DLQ after {retry_count} retries")
            return False

        delay = self._backoff_delay(retry_count)
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)
        self.repo.schedule_retry(outbox_id, scheduled_at=scheduled_at, error=error)
        logger.info(f"Outbox {outbox_id} retry #{retry_count} scheduled in {delay}s")
        return True

    def get_due_retries(self, batch_size: int = 50) -> list[str]:
        """Get outbox messages due for retry."""
        return self.repo.get_due_retries(batch_size=batch_size)

    def _backoff_delay(self, retry_count: int) -> int:
        delay = self.policy["base_delay_seconds"] * (self.policy["backoff_factor"] ** (retry_count - 1))
        return min(int(delay), self.policy["max_delay_seconds"])
