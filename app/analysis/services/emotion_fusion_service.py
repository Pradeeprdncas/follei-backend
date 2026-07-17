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
        if cls.engine is None:
            cls.initialize()
        return cls.engine.fuse(
            voice_emotion=voice_emotion,
            voice_confidence=voice_confidence,
            text_emotion=text_emotion,
            text_confidence=text_confidence,
            voice_probabilities=voice_probabilities,
            text_probabilities=text_probabilities,
        )
