"""Embedding worker — processes chunk.embedded events, generates vector embeddings."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class EmbeddingWorker:
    """Consumes document.processed events, generates embeddings, indexes to Qdrant."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-embedding-group")
        logger.info("Embedding worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down embedding worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement embedding generation

    def _shutdown(self, signum=None, frame=None):
        self.running = False
