from __future__ import annotations

from app.analysis.pipelines.emotion_fusion import EmotionFusionEngine, EmotionFusionResult


class EmotionFusionService:
    engine: EmotionFusionEngine | None = None

    @classmethod
    def initialize(cls) -> None:
        if cls.engine is None:
            cls.engine = EmotionFusionEngine()

    @classmethod
    def fuse(
        cls,
        voice_emotion: str,
        voice_confidence: float,
        text_emotion: str,
        text_confidence: float,
        voice_probabilities: dict[str, float] | None = None,
        text_probabilities: dict[str, float] | None = None,
    ) -> EmotionFusionResult:
        """Adapts this service's (voice, text) naming to the engine's
        (text_sentiment, voice_emotion) signature. voice/text_probabilities
        aren't part of the engine's weighting algorithm — accepted here only
        so callers that already compute them don't need special-casing.
        """
        if cls.engine is None:
            cls.initialize()
        return cls.engine.fuse(
            text_sentiment=text_emotion,
            text_confidence=text_confidence,
            voice_emotion=voice_emotion,
            voice_confidence=voice_confidence,
        )
