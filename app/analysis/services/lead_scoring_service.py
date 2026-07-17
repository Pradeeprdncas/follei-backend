import logging
from typing import Any, Dict, Optional

from app.analysis.services.lead_intelligence_service import LeadIntelligenceService

logger = logging.getLogger(__name__)


class LeadScoringService:
    @classmethod
    def calculate_lead_scores(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        return LeadIntelligenceService.calculate_lead_scores(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )

    @classmethod
    def predict_conversion(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        return LeadIntelligenceService.predict_conversion(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )

    @classmethod
    def categorize_lead(cls, lead_score: float) -> str:
        return LeadIntelligenceService.categorize_lead(lead_score)

    @classmethod
    def generate_next_action(
        cls,
        lead_score: float,
        scores: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> str:
        return LeadIntelligenceService.generate_next_action(lead_score, scores=scores, text=text)

    @classmethod
    def update_customer_profile(
        cls,
        session_id: str,
        profile: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return LeadIntelligenceService.update_customer_profile(session_id, profile=profile, metadata=metadata)

    @classmethod
    def store_lead_history(
        cls,
        session_id: str,
        payload: Dict[str, Any],
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        return LeadIntelligenceService.store_lead_history(session_id, payload, text=text)

    @classmethod
    def score(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        return LeadIntelligenceService.score(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )
