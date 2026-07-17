"""CRM sync worker — processes crm.sync.requested events for external CRM integration."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class CrmSyncWorker:
    """Consumes crm.sync.requested events and syncs to external CRM providers."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-crm-group")
        logger.info("CRM sync worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down CRM sync worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement CRM sync

    def _shutdown(self, signum=None, frame=None):
        self.running = False
