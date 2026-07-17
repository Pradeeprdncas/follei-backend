"""Sentiment analysis pipeline stage."""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from app.analysis.sentiment.provider import SentimentProvider
from loguru import logger


class SentimentStage(AnalysisStage):
    """Analyzes sentiment from the transcript text."""

    def __init__(self, provider: SentimentProvider | None = None):
        self._provider = provider

    @property
    def name(self) -> str:
        return "sentiment"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        text = ctx.transcript
        if not text:
            logger.warning("No transcript for sentiment analysis — skipping")
            return ctx

        if not self._provider:
            logger.info("No sentiment provider configured — using heuristic")
            ctx.sentiment = self._heuristic(text)
            return ctx

        try:
            result = await self._provider.analyze(text)
            ctx.sentiment = {
                "overall": result.overall_label,
                "overall_confidence": result.overall_confidence,
                "timeline": [
                    {
                        "start_sec": s.start_sec,
                        "end_sec": s.end_sec,
                        "label": s.label,
                        "confidence": s.confidence,
                        "text": s.text,
                    }
                    for s in result.segments
                ],
            }
            logger.info(f"Sentiment: {result.overall_label} ({result.overall_confidence:.2f})")
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")

        return ctx

    def _heuristic(self, text: str) -> dict:
        """Simple keyword-based sentiment fallback."""
        positive_words = {"good", "great", "excellent", "happy", "love", "thanks", "perfect", "yes"}
        negative_words = {"bad", "terrible", "awful", "hate", "angry", "no", "never", "wrong"}

        words = set(text.lower().split())
        pos_count = len(words & positive_words)
        neg_count = len(words & negative_words)

        if pos_count > neg_count:
            label = "positive"
        elif neg_count > pos_count:
            label = "negative"
        else:
            label = "neutral"

        confidence = min(0.9, max(0.5, (pos_count + neg_count) * 0.1))
        return {
            "overall": label,
            "overall_confidence": round(confidence, 2),
            "timeline": [{"start_sec": 0, "end_sec": 0, "label": label, "confidence": round(confidence, 2)}],
        }
