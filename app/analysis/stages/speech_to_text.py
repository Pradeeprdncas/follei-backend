"""STT pipeline stage — transcribes audio to text via configured provider."""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from app.analysis.speech.provider import STTProvider
from loguru import logger


class SpeechToTextStage(AnalysisStage):
    """Transcribes audio using the configured STT provider.

    Skips transcription if the context already contains a transcript
    (i.e., when run_transcript was used).
    """

    def __init__(self, provider: STTProvider | None = None):
        self._provider = provider

    @property
    def name(self) -> str:
        return "speech_to_text"

    @property
    def enabled(self) -> bool:
        return True

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.transcript:
            logger.info("Transcript already present — skipping STT")
            return ctx

        if not ctx.audio_path and not ctx.audio_bytes:
            logger.warning("No audio input for STT — skipping")
            return ctx

        if not self._provider:
            logger.warning("No STT provider configured — skipping")
            return ctx

        try:
            if ctx.audio_path:
                result = await self._provider.transcribe_file(ctx.audio_path)
            else:
                result = await self._provider.transcribe(ctx.audio_bytes)

            ctx.transcript = result.full_text
            ctx.segments = [
                {
                    "start_sec": s.start_sec,
                    "end_sec": s.end_sec,
                    "text": s.text,
                    "confidence": s.confidence,
                    "speaker": s.speaker,
                }
                for s in result.segments
            ]
            ctx.duration_seconds = result.duration_sec
            logger.info(f"STT completed: {len(result.segments)} segments, {result.duration_sec:.1f}s")
        except Exception as e:
            logger.error(f"STT failed: {e}")
            ctx.error = f"speech_to_text: {e}"

        return ctx
