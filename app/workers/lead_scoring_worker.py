"""Lead scoring worker — persists computed lead intelligence scores.

Consumes EVENT_CONVERSATION_ANALYSIS_COMPLETED (published both by the live
voice path in app/api/websocket_handler.py and by the async/API-triggered
app/analysis/workers/analysis_worker.py), writes a LeadScore row capturing
the full ICP/Intent/Engagement/Qualification/BuyingSignal/Relationship +
BANT/MEDDIC payload, and updates Lead.current_score/current_temperature so
the rest of the app (routers, other workers) can read a lead's latest state
without re-deriving it from raw conversation analyses.
"""
import json
import uuid
from datetime import datetime

from app.analysis.services.event_bus import EVENT_CONVERSATION_ANALYSIS_COMPLETED
from app.analysis.services.lead_intelligence_service import LeadIntelligenceService
from app.events.base import EVENT_LEAD_SCORE_UPDATED, EVENT_LEAD_TEMPERATURE_CHANGED
from app.events.publisher import DomainEventPublisher
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation
from app.models.leads.lead import Lead
from app.models.leads.lead_score import LeadScore
from loguru import logger

_settings = get_settings()


class LeadScoringWorker:
    """Consumes conversation.analysis.completed events and persists lead scores."""

    def __init__(self):
        self.running = True
        self.event_publisher = DomainEventPublisher(source="lead_scoring.worker")

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-lead-scoring-group")
        logger.info("Lead scoring worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                if not records:
                    continue
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down lead scoring worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        try:
            value = message.value
            # The producer double-encodes (DomainEvent.to_json() already
            # returns a JSON string, then the Kafka value_serializer
            # json.dumps's it again) — mirrors the same defensive unwrap
            # app/analysis/workers/analysis_worker.py uses for the same reason.
            if isinstance(value, str):
                value = json.loads(value)

            event_type = value.get("event_type") or message.key
            if event_type != EVENT_CONVERSATION_ANALYSIS_COMPLETED:
                return

            data = value.get("data", {})
            tenant_id = data.get("tenant_id") or value.get("tenant_id")
            conversation_id = data.get("conversation_id")
            lead_score_payload = data.get("lead_score") or {}
            if not conversation_id or not lead_score_payload:
                return

            self._persist(tenant_id, conversation_id, lead_score_payload)
        except Exception:
            logger.exception(f"Failed to process lead scoring event: {message}")

    def _persist(self, tenant_id: str | None, conversation_id: str, payload: dict) -> None:
        composite = payload.get("lead_score")
        if composite is None:
            composite = payload.get("overall")
        if composite is None:
            logger.debug(f"No numeric lead_score in payload for conversation={conversation_id}; skipping")
            return

        with SessionLocal() as session:
            conversation = session.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conversation or not conversation.lead_id:
                logger.debug(f"Conversation {conversation_id} has no linked lead; skipping score persistence")
                return

            lead = session.query(Lead).filter(Lead.id == conversation.lead_id).first()
            if not lead:
                return

            previous_score = lead.current_score
            previous_temperature = lead.current_temperature
            score_value = float(composite)
            temperature = LeadIntelligenceService.categorize_score(score_value)

            score_row = LeadScore(
                id=uuid.uuid4(),
                lead_id=lead.id,
                tenant_id=lead.tenant_id,
                score=int(round(score_value)),
                previous_score=int(round(previous_score)) if previous_score is not None else None,
                score_delta=int(round(score_value - previous_score)) if previous_score is not None else None,
                event_type="conversation_analysis",
                event_metadata=payload,
            )
            session.add(score_row)

            lead.current_score = score_value
            lead.current_temperature = temperature
            lead.last_analysis_at = datetime.utcnow()
            confidence = payload.get("confidence")
            if confidence is not None:
                lead.analysis_confidence = float(confidence)

            session.commit()
            logger.info(
                f"Lead {lead.id} score updated: {previous_score} -> {score_value} "
                f"({previous_temperature} -> {temperature})"
            )

        self.event_publisher.publish(EVENT_LEAD_SCORE_UPDATED, str(tenant_id or lead.tenant_id), {
            "lead_id": str(lead.id),
            "conversation_id": conversation_id,
            "score": score_value,
            "previous_score": previous_score,
            "temperature": temperature,
        })
        if temperature != previous_temperature:
            self.event_publisher.publish(EVENT_LEAD_TEMPERATURE_CHANGED, str(tenant_id or lead.tenant_id), {
                "lead_id": str(lead.id),
                "conversation_id": conversation_id,
                "previous_temperature": previous_temperature,
                "temperature": temperature,
            })

    def _shutdown(self, signum=None, frame=None):
        self.running = False


if __name__ == "__main__":
    worker = LeadScoringWorker()
    worker.run()
