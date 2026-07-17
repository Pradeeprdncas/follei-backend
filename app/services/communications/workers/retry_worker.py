"""Retry worker — processes outbox messages due for retry."""
import asyncio
from loguru import logger

from app.repositories.outbox import OutboxRepository
from app.services.communications.outbox import OutboxService
from app.services.communications.router import CommunicationRouter
from app.services.communications.retry import RetryEngine
from app.database.session import SessionLocal


class RetryWorker:
    """Picks up due retries and re-attempts delivery."""

    def run_once(self, batch_size: int = 30) -> int:
        db = SessionLocal()
        try:
            repo = OutboxRepository(db)
            router = CommunicationRouter()
            retry = RetryEngine(repo)
            svc = OutboxService(repo, router, retry)

            due_ids = retry.get_due_retries(batch_size=batch_size)
            processed = 0
            for oid in due_ids:
                result = asyncio.run(svc.send_sync(oid))
                if not result.success:
                    retry.schedule_retry(oid, result.error or "Unknown")
                processed += 1
            db.commit()
            return processed
        except Exception as e:
            logger.error(f"Retry worker error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()
