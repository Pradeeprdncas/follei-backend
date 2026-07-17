"""Cleanup worker — purges stale outbox/expired events."""
from datetime import datetime, timedelta
from loguru import logger

from app.repositories.outbox import OutboxRepository
from app.database.session import SessionLocal


class CleanupWorker:
    """Removes stale outbox messages and expired provider logs."""

    def run_once(self, retention_hours: int = 72) -> int:
        db = SessionLocal()
        try:
            repo = OutboxRepository(db)
            cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
            deleted = repo.purge_completed(before=cutoff)
            db.commit()
            logger.info(f"Cleanup: purged {deleted} stale outbox messages")
            return deleted
        except Exception as e:
            logger.error(f"Cleanup worker error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()
