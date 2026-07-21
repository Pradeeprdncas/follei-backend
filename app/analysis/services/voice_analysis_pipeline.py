from __future__ import annotations

import logging
from typing import Any

from app.analysis.services.voice_emotion_service import VoiceEmotionService
from app.analysis.services.text_sentiment_service import SentimentService
from app.analysis.services.emotion_fusion_service import EmotionFusionService
from app.analysis.services.lead_scoring_service import LeadScoringService
from app.analysis.services.learned_bant_service import LearnedBANTService

logger = logging.getLogger(__name__)


class VoiceAnalysisPipeline:
    """Orchestrates the full analysis pipeline for a voice interaction.

    Order:
      1. Voice emotion → VoiceEmotionService
      2. Text sentiment → SentimentService
      3. Emotion fusion → EmotionFusionService
      4. Lead scoring → LeadScoringService
      5. BANT/MEDDIC → LearnedBANTService (LLM fallback if no trained model)
    """

    @classmethod
    def initialize(cls) -> None:
        VoiceEmotionService.initialize()
        SentimentService.initialize()

    @classmethod
    async def analyze(
        cls,
        text: str,
        audio=None,
        history: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        crm_context: dict[str, Any] | None = None,
        business_docs: list[str] | None = None,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        lead_id: str | None = None,
    ) -> dict[str, Any]:
        text_sentiment = SentimentService.analyze(text)

        voice_result = None
        if audio is not None:
            voice_result = VoiceEmotionService.predict(audio)

        if voice_result is not None:
            fusion = EmotionFusionService.fuse(
                voice_emotion=voice_result.emotion,
                voice_confidence=voice_result.confidence,
                voice_probabilities=voice_result.probabilities,
                text_emotion=text_sentiment.get("sentiment", "neutral"),
                text_confidence=text_sentiment.get("confidence", 0.5),
                text_probabilities=text_sentiment.get("probabilities"),
            )
        else:
            fusion = None

        lead_scores = LeadScoringService.score(
            text,
            voice_emotion=voice_result.emotion if voice_result else None,
            emotion_confidence=voice_result.confidence if voice_result else None,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )
        # LeadScoringService.score() has no "confidence" key of its own — the
        # closest analogue is the conversion-probability fraction it already
        # computes, so surface it under that name for UI consumers that show
        # "lead score / confidence" side by side (e.g. app/static/user_console.html).
        lead_scores.setdefault("confidence", lead_scores.get("conversion_probability"))

        bant_scores = await LearnedBANTService.predict(
            text,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            lead_id=lead_id,
        )

        result = {
            "text": text,
            "sentiment": text_sentiment,
        }
        if voice_result is not None:
            result["voice_emotion"] = {
                "emotion": voice_result.emotion,
                "confidence": voice_result.confidence,
                "probabilities": voice_result.probabilities,
            }
        if fusion is not None:
            result["fusion"] = {
                "fused_emotion": fusion.final_emotion,
                "fused_confidence": fusion.confidence,
            }
        result["lead_scores"] = lead_scores
        result["bant"] = bant_scores

        return result
