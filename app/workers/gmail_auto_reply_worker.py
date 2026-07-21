"""Gmail auto-reply worker — polls the monitored mailbox on an interval.

Standalone process, same shape as the other app/workers/*.py entrypoints. Each
tick fetches unread mail and auto-replies via GmailAutoReplyService.poll_once().
Run with: python -m app.workers.gmail_auto_reply_worker
"""
import asyncio

from loguru import logger

from app.config.settings import get_settings
from app.services.communications.gmail_auto_reply import GmailAutoReplyService

_settings = get_settings()


class GmailAutoReplyWorker:
    def __init__(self):
        self.running = True
        self.service = GmailAutoReplyService()

    async def run(self) -> None:
        interval = _settings.GMAIL_POLL_INTERVAL_SECONDS
        logger.info(
            f"Gmail auto-reply worker started (mailbox={_settings.GMAIL_MONITORED_EMAIL}, "
            f"interval={interval}s, enabled={_settings.GMAIL_AUTO_REPLY_ENABLED})"
        )
        while self.running:
            try:
                results = await self.service.poll_once()
                replied = sum(1 for r in results if r.get("auto_replied"))
                if results:
                    logger.info(f"Gmail poll: {len(results)} unread, {replied} auto-replied")
            except Exception as exc:
                logger.error(f"Gmail poll cycle failed: {exc}")
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self.running = False


if __name__ == "__main__":
    worker = GmailAutoReplyWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Gmail auto-reply worker stopped")
