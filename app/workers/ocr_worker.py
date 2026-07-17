"""OCR worker — processes document.uploaded events for PDF/image OCR."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class OCRWorker:
    """Consumes document.uploaded events, runs OCR, publishes chunks."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-ocr-group")
        logger.info("OCR worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down OCR worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement OCR pipeline

    def _shutdown(self, signum=None, frame=None):
        self.running = False
