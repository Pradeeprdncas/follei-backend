"""Kafka consumer that processes conversation analysis requests.

Consumes from `domain-events` topic, filters for `conversation.analysis.requested`
events, runs the analysis pipeline, and publishes results.

Designed to run as a standalone process alongside the main backend.
"""
import asyncio
import json
import signal
import sys
import platform
import time

# ── Model registration (must precede any service that touches the DB) ──────
# ConversationAnalysis.relationship("Conversation") requires Conversation to
# be in Base.registry before configure_mappers() fires on first DB access.
from app.models import Conversation  # noqa: F401
from app.analysis.models import ConversationAnalysis  # noqa: F401

from app.analysis.pipelines.conversation import ConversationAnalysisPipeline
from app.analysis.services.conversation_analysis_service import ConversationAnalysisService
from app.analysis.verification.validator import AnalysisOutputValidator
from app.analysis.services.event_bus import DomainEventPublisher, EVENT_CONVERSATION_ANALYSIS_COMPLETED
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class AnalysisWorker:
    """Kafka consumer for conversation analysis requests.

    Usage:
        worker = AnalysisWorker()
        worker.run()
    """

    def __init__(self):
        self.running = True
        self.validator = AnalysisOutputValidator()
        self.analysis_service = ConversationAnalysisService(validator=self.validator)
        self.event_publisher = DomainEventPublisher(source="analysis.worker")
        self.pipeline = ConversationAnalysisPipeline(validator=self.validator)

        # Register signals
        signal.signal(signal.SIGINT, self._shutdown)
        if platform.system() != "Windows":
            signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum=None, frame=None):
        logger.info("Shutdown signal received — stopping worker...")
        self.running = False

    def run(self):
        """Main consumer loop.

        kafka-python occasionally tears down a broker connection (idle
        timeout, broker restart) and leaves a closed socket (fd=-1) behind;
        the next poll() then raises ValueError("Invalid file descriptor: -1")
        instead of a Kafka-specific error, which used to bubble out of the
        single poll loop below and kill the whole worker process after one
        transient hiccup. Recreating the consumer and retrying keeps the
        worker alive across that instead of requiring a manual restart.
        """
        ensure_topics()
        logger.info("Analysis worker started — waiting for events...")
        consumer = None

        while self.running:
            try:
                if consumer is None:
                    consumer = get_consumer(
                        _settings.KAFKA_TOPIC_DOMAIN_EVENTS,
                        _settings.KAFKA_CONSUMER_GROUP_ANALYSIS,
                    )

                records = consumer.poll(timeout_ms=1000)
                if not records:
                    continue

                for topic_partition, messages in records.items():
                    for message in messages:
                        if not self.running:
                            break
                        self._process_message(message)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt — shutting down")
                break
            except Exception as e:
                logger.warning(f"Kafka consumer error, reconnecting: {e}")
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass
                consumer = None
                if self.running:
                    time.sleep(2)

        if consumer is not None:
            consumer.close()
        logger.info("Analysis worker stopped")

    def _process_message(self, message) -> None:
        """Process a single Kafka message."""
        try:
            value = message.value
            if isinstance(value, str):
                value = json.loads(value)

            event_type = value.get("event_type") or message.key
            if event_type != "conversation.analysis.requested":
                return

            data = value.get("data", {})
            tenant_id = data.get("tenant_id", value.get("tenant_id", ""))
            conversation_id = data.get("conversation_id", "")

            if not conversation_id or not tenant_id:
                logger.warning(f"Skipping event — missing conversation_id or tenant_id: {value}")
                return

            logger.info(f"Processing analysis for conversation {conversation_id}")

            # Ensure analysis record exists
            self.analysis_service.create_analysis(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
            )

            # Run pipeline
            if data.get("audio_path"):
                result = asyncio.run(
                    self.pipeline.run_file(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        audio_path=data["audio_path"],
                    )
                )
            elif data.get("transcript"):
                result = asyncio.run(
                    self.pipeline.run_transcript(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        transcript=data["transcript"],
                    )
                )
            else:
                logger.error(f"No audio_path or transcript in event: {data}")
                self.analysis_service.mark_failed(conversation_id, "No input data")
                return

            # Persist validated results
            saved = self.analysis_service.update_complete_analysis(
                conversation_id=conversation_id,
                analysis=result.to_dict(),
            )

            if saved:
                self.event_publisher.publish(
                    event_type=EVENT_CONVERSATION_ANALYSIS_COMPLETED,
                    tenant_id=tenant_id,
                    data={
                        "conversation_id": conversation_id,
                        "status": "completed",
                        "lead_score": result.lead_score,
                        "summary": result.summary,
                    },
                )
                logger.info(f"Analysis completed for conversation {conversation_id}")

        except Exception as e:
            logger.exception(f"Failed to process message: {e}")


if __name__ == "__main__":
    worker = AnalysisWorker()
    worker.run()
