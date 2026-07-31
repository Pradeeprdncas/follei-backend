"""Campaign worker — processes campaign.launched events, sends messages."""
import asyncio

from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class CampaignWorker:
    """Consumes campaign.launched events and orchestrates message delivery."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-campaign-group")
        logger.info("Campaign worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
                if records:
                    consumer.commit()
        except KeyboardInterrupt:
            logger.info("Shutting down campaign worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        payload = message.value if hasattr(message, "value") else message
        if not isinstance(payload, dict):
            return
        event_type = payload.get("event_type") or payload.get("type")
        if event_type != "campaign.launched":
            return
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        campaign_id = data.get("campaign_id")
        if not campaign_id:
            logger.warning("campaign.launched event missing campaign_id")
            return
        from app.database.session import SessionLocal
        from app.services.campaigns.service import CampaignService
        with SessionLocal() as db:
            result = asyncio.run(CampaignService(db).start(str(campaign_id)))
        logger.info("Campaign {} queued: {}", campaign_id, result.get("status"))

    def _shutdown(self, signum=None, frame=None):
        self.running = False
