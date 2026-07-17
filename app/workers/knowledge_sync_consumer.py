"""Background worker for durable knowledge synchronization events."""
from __future__ import annotations

import asyncio
import signal
from time import sleep

from loguru import logger

from app.services.knowledge.outbox import process_pending_events


class KnowledgeSyncWorker:
    def __init__(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *_args) -> None:
        self.running = False

    def run(self) -> None:
        logger.info("Knowledge sync worker started")
        while self.running:
            try:
                processed = asyncio.run(process_pending_events())
                sleep(0.25 if processed else 2.0)
            except Exception as exc:
                logger.exception(f"Knowledge sync worker retrying after error: {exc}")
                sleep(2.0)
        logger.info("Knowledge sync worker stopped")


if __name__ == "__main__":
    KnowledgeSyncWorker().run()