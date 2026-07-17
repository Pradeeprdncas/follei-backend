"""Emotion detection pipeline stage."""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from app.analysis.emotion.provider import EmotionProvider
from loguru import logger


class EmotionStage(AnalysisStage):
    """Detects emotion from audio via the configured emotion provider."""

    def __init__(self, provider: EmotionProvider | None = None):
        self._provider = provider

    @property
    def name(self) -> str:
        return "emotion"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not self._provider:
            logger.info("No emotion provider configured — skipping")
            return ctx

        if not ctx.audio_path and not ctx.audio_bytes:
            logger.info("No audio for emotion detection — skipping")
            return ctx

        try:
            if ctx.audio_path:
                result = await self._provider.recognize_file(ctx.audio_path)
            else:
                result = await self._provider.recognize(ctx.audio_bytes)

            ctx.emotion = {
                "overall": result.overall_label,
                "overall_confidence": result.overall_confidence,
                "timeline": [
                    {
                        "start_sec": s.start_sec,
                        "end_sec": s.end_sec,
                        "label": s.label,
                        "confidence": s.confidence,
                        "probabilities": s.probabilities,
                    }
                    for s in result.segments
                ],
            }
            logger.info(f"Emotion: {result.overall_label} ({result.overall_confidence:.2f})")
        except Exception as e:
            logger.error(f"Emotion detection failed: {e}")

        return ctx
