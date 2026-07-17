"""Email worker — consumes outbox messages and sends via email provider."""
import asyncio
from loguru import logger

from app.repositories.outbox import OutboxRepository
from app.services.communications.outbox import OutboxService
from app.services.communications.router import CommunicationRouter
from app.services.communications.retry import RetryEngine
from app.database.session import SessionLocal


class EmailWorker:
    """Processes email outbox messages."""

    def __init__(self):
        self.running = True

    def run_once(self, batch_size: int = 20) -> int:
        db = SessionLocal()
        try:
            repo = OutboxRepository(db)
            router = CommunicationRouter()
            retry = RetryEngine(repo)
            svc = OutboxService(repo, router, retry)
            outbox_ids = repo.dequeue_by_channel("email", batch_size=batch_size)
            processed = 0
            for oid in outbox_ids:
                result = asyncio.run(svc.send_sync(oid))
                if not result.success:
                    retry.schedule_retry(oid, result.error or "Unknown")
                processed += 1
            db.commit()
            return processed
        except Exception as e:
            logger.error(f"Email worker error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()
