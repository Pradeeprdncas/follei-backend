"""Domain service for managing conversation analysis CRUD.

Uses the separate conversation_analyses table with 1:1 relationship
to conversations. All analysis data is validated before persistence.
"""
import uuid
from datetime import datetime
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.analysis.models.conversation_analysis import ConversationAnalysis
from app.analysis.verification.validator import AnalysisOutputValidator
from app.database.session import SessionLocal
from loguru import logger


class ConversationAnalysisService:
    """Service for analysis CRUD — wraps the conversation_analyses table."""

    def __init__(self, validator: AnalysisOutputValidator | None = None):
        self.validator = validator or AnalysisOutputValidator()

    # ── Write ───────────────────────────────────────────────────

    def create_analysis(
        self,
        conversation_id: str,
        tenant_id: str,
    ) -> ConversationAnalysis:
        """Create an empty analysis record linked to a conversation."""
        with SessionLocal() as session:
            existing = (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.conversation_id == conversation_id)
                .first()
            )
            if existing:
                logger.warning(f"Analysis already exists for conversation {conversation_id}")
                return existing

            record = ConversationAnalysis(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                status="pending",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Created analysis record {record.id} for conversation {conversation_id}")
            return record

    def update_transcript(
        self,
        conversation_id: str,
        transcript: dict,
    ) -> bool:
        """Validate and persist transcript. Returns True if saved."""
        vr = self.validator.validate_transcript(transcript)
        if not vr.valid:
            logger.error(f"Transcript validation failed for {conversation_id}: {vr.errors}")
            return False
        return self._update_field(conversation_id, "transcript", transcript)

    def update_sentiment(
        self,
        conversation_id: str,
        sentiment: dict,
    ) -> bool:
        """Validate and persist sentiment. Returns True if saved."""
        vr = self.validator.validate_sentiment(sentiment)
        if not vr.valid:
            logger.error(f"Sentiment validation failed for {conversation_id}: {vr.errors}")
            return False
        return self._update_field(conversation_id, "sentiment", sentiment)

    def update_emotion(
        self,
        conversation_id: str,
        emotion: dict,
    ) -> bool:
        """Validate and persist emotion. Returns True if saved."""
        vr = self.validator.validate_emotion(emotion)
        if not vr.valid:
            logger.error(f"Emotion validation failed for {conversation_id}: {vr.errors}")
            return False
        return self._update_field(conversation_id, "emotion", emotion)

    def update_lead_score(
        self,
        conversation_id: str,
        lead_score: dict,
    ) -> bool:
        """Validate and persist lead score. Returns True if saved."""
        vr = self.validator.validate_lead_score(lead_score)
        if not vr.valid:
            logger.error(f"Lead score validation failed for {conversation_id}: {vr.errors}")
            return False
        return self._update_field(conversation_id, "lead_score", lead_score)

    def update_complete_analysis(
        self,
        conversation_id: str,
        analysis: dict,
    ) -> bool:
        """Validate and persist a complete analysis dict.

        This is the primary write method called by the pipeline.
        All fields are validated before writing to ensure no bad data
        reaches the database.
        """
        vr = self.validator.validate_all(analysis)
        if not vr.valid:
            logger.error(f"Complete analysis validation failed for {conversation_id}: {vr.errors}")
            return False

        with SessionLocal() as session:
            record = (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.conversation_id == conversation_id)
                .first()
            )
            if not record:
                logger.error(f"Analysis record not found for conversation {conversation_id}")
                return False

            record.transcript = analysis.get("transcript", {})
            record.sentiment = analysis.get("sentiment", {})
            record.emotion = analysis.get("emotion", {})
            record.fusion = analysis.get("fusion", {})
            record.lead_score = analysis.get("lead_score", {})
            record.claims = analysis.get("claims", [])
            record.verification = analysis.get("verification", [])
            record.summary = analysis.get("summary")
            record.speakers = analysis.get("speakers", [])
            record.duration_seconds = analysis.get("duration_seconds")
            record.status = "completed"
            record.updated_at = datetime.utcnow()

            session.commit()
            logger.info(f"Complete analysis saved for conversation {conversation_id}")
            return True

    def mark_failed(self, conversation_id: str, error_message: str) -> None:
        with SessionLocal() as session:
            record = (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.conversation_id == conversation_id)
                .first()
            )
            if record:
                record.status = "failed"
                record.error_message = error_message
                record.updated_at = datetime.utcnow()
                session.commit()

    # ── Read ────────────────────────────────────────────────────

    def get_analysis(self, conversation_id: str) -> ConversationAnalysis | None:
        with SessionLocal() as session:
            return (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.conversation_id == conversation_id)
                .first()
            )

    def get_analysis_by_id(self, analysis_id: str) -> ConversationAnalysis | None:
        with SessionLocal() as session:
            return (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.id == analysis_id)
                .first()
            )

    def list_analyses(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationAnalysis]:
        with SessionLocal() as session:
            query = session.query(ConversationAnalysis).filter(
                ConversationAnalysis.tenant_id == tenant_id
            )
            if status:
                query = query.filter(ConversationAnalysis.status == status)
            return query.order_by(ConversationAnalysis.created_at.desc()).offset(offset).limit(limit).all()

    # ── Helpers ─────────────────────────────────────────────────

    def _update_field(self, conversation_id: str, field: str, value: dict) -> bool:
        with SessionLocal() as session:
            rows = (
                session.query(ConversationAnalysis)
                .filter(ConversationAnalysis.conversation_id == conversation_id)
                .update(
                    {field: value, "updated_at": datetime.utcnow()},
                    synchronize_session="fetch",
                )
            )
            session.commit()
            return rows > 0
