"""Runs Gmail inbound polling, scheduled campaigns, email outbox, and retries."""
from __future__ import annotations

import asyncio
import signal

from loguru import logger

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.repositories.campaign import CampaignRepository
from app.services.campaigns.service import CampaignService
from app.services.communications.gmail_auto_reply import GmailAutoReplyService
from app.services.communications.workers.email_worker import EmailWorker
from app.services.communications.workers.retry_worker import RetryWorker

_settings = get_settings()


class MailOperationsWorker:
    def __init__(self):
        self.running = True
        self._stop_event: asyncio.Event | None = None
        self.gmail = GmailAutoReplyService()
        self.email_worker = EmailWorker()
        self.retry_worker = RetryWorker()

    async def _start_due_campaigns(self) -> int:
        db = SessionLocal()
        try:
            campaigns = CampaignRepository(db).get_scheduled_pending()
            started = 0
            for campaign in campaigns:
                try:
                    await CampaignService(db).start(str(campaign.id))
                    started += 1
                except Exception as exc:
                    db.rollback()
                    logger.error("Scheduled campaign {} failed to queue: {}", campaign.id, exc)
            return started
        finally:
            db.close()

    async def run_once(self) -> dict:
        gmail_results = await self.gmail.poll_once()
        campaigns_started = await self._start_due_campaigns()
        sent = await asyncio.to_thread(self.email_worker.run_once, 50)
        retried = await asyncio.to_thread(self.retry_worker.run_once, 50)
        return {
            "inbound_checked": len(gmail_results),
            "campaigns_started": campaigns_started,
            "outbox_processed": sent,
            "retries_processed": retried,
        }

    async def run(self) -> None:
        interval = max(5, min(int(_settings.GMAIL_POLL_INTERVAL_SECONDS or 60), 60))
        self._stop_event = asyncio.Event()
        logger.info("Mail operations worker started (interval={}s)", interval)
        while self.running:
            try:
                summary = await self.run_once()
                if any(summary.values()):
                    logger.info("Mail operations cycle: {}", summary)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Mail operations cycle failed: {}", exc)
            if not self.running:
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
        logger.info("Mail operations worker stopped cleanly")

    def stop(self) -> None:
        self.running = False
        if self._stop_event is not None:
            self._stop_event.set()


def _install_signal_handlers(worker: MailOperationsWorker) -> None:
    """Convert terminal/service stop signals into a normal zero-code exit."""
    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        handled_signal = getattr(signal, signal_name, None)
        if handled_signal is not None:
            signal.signal(handled_signal, lambda *_args: worker.stop())


if __name__ == "__main__":
    worker = MailOperationsWorker()
    _install_signal_handlers(worker)
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        worker.stop()
        logger.info("Mail operations worker interrupted")
