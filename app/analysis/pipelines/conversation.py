"""Conversation analysis pipeline — orchestrates analysis of a conversation.

The pipeline is designed as a configurable sequence of pluggable stages.
Each stage is self-contained, independently testable, and wired via the
StageRegistry.

Supports three input modes:
1. Audio file (path on disk) → STT → full analysis
2. Raw transcript (text) → skip STT → full analysis
3. Streaming (future) → per-chunk incremental analysis

Output is a single AnalysisResult dict validated before return.
"""
from dataclasses import dataclass, field
from typing import Any

from app.analysis.stages.registry import StageRegistry
from app.analysis.verification.validator import AnalysisOutputValidator
from app.analysis.fusion.engine import fuse
from app.analysis.lead_scoring.scorer import score_conversation
from loguru import logger


@dataclass
class AnalysisResult:
    conversation_id: str
    tenant_id: str
    transcript: dict = field(default_factory=dict)
    sentiment: dict = field(default_factory=dict)
    emotion: dict = field(default_factory=dict)
    fusion: dict = field(default_factory=dict)
    lead_score: dict = field(default_factory=dict)
    claims: list[dict] = field(default_factory=list)
    verification: list[dict] = field(default_factory=list)
    summary: str | None = None
    speakers: list[dict] = field(default_factory=list)
    duration_seconds: float | None = None
    status: str = "completed"
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "tenant_id": self.tenant_id,
            "transcript": self.transcript,
            "sentiment": self.sentiment,
            "emotion": self.emotion,
            "fusion": self.fusion,
            "lead_score": self.lead_score,
            "claims": self.claims,
            "verification": self.verification,
            "summary": self.summary,
            "speakers": self.speakers,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "error": self.error,
        }


class ConversationAnalysisPipeline:
    """Configurable pipeline for conversation analysis.

    Usage:
        pipeline = ConversationAnalysisPipeline(registry=my_registry)
        result = await pipeline.run_file(tenant_id="...", conversation_id="...", audio_path="...")
        result = await pipeline.run_transcript(tenant_id="...", conversation_id="...", transcript="...")
    """

    def __init__(
        self,
        registry: StageRegistry | None = None,
        validator: AnalysisOutputValidator | None = None,
    ):
        self.registry = registry or self._default_registry()
        self.validator = validator or AnalysisOutputValidator()

    async def run_file(
        self,
        tenant_id: str,
        conversation_id: str,
        audio_path: str,
    ) -> AnalysisResult:
        """Analyze an audio file: STT → sentiment → emotion → fusion → claims → lead score."""
        from app.analysis.stages.base import PipelineContext

        ctx = PipelineContext(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            audio_path=audio_path,
        )
        ctx = self.registry.execute(ctx)
        return self._context_to_result(ctx)

    async def run_transcript(
        self,
        tenant_id: str,
        conversation_id: str,
        transcript: str,
    ) -> AnalysisResult:
        """Analyze a pre-existing transcript (skip STT)."""
        from app.analysis.stages.base import PipelineContext

        ctx = PipelineContext(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            transcript=transcript,
        )
        ctx = self.registry.execute(ctx)
        return self._context_to_result(ctx)

    async def run_stream(
        self,
        tenant_id: str,
        conversation_id: str,
    ):
        """Streaming analysis (plumbing ready — implementation TBD).

        Yields partial AnalysisResult as segments are processed.
        """
        raise NotImplementedError("Streaming pipeline — implement async generator per-segment")

    # ── Internal ────────────────────────────────────────────────

    def _context_to_result(self, ctx) -> AnalysisResult:
        result = AnalysisResult(
            conversation_id=ctx.conversation_id,
            tenant_id=ctx.tenant_id,
            transcript={
                "segments": ctx.segments or [],
                "full_text": ctx.transcript or "",
            } if ctx.transcript or ctx.segments else {},
            sentiment=ctx.sentiment or {},
            emotion=ctx.emotion or {},
            lead_score=ctx.lead_score or {},
            claims=ctx.claims or [],
            verification=ctx.verification or [],
            summary=ctx.summary,
            speakers=ctx.speakers or [],
            duration_seconds=ctx.duration_seconds,
            status="failed" if ctx.error else "completed",
            error=ctx.error,
        )

        # Fusion is computed from sentiment + emotion if not already set
        if not result.fusion:
            fusion_result = fuse(result.sentiment, result.emotion)
            result.fusion = {
                "final": fusion_result.final_emotion,
                "confidence": fusion_result.confidence,
                "reason": fusion_result.reason,
            }

        # Lead score is computed from all available data if not already set
        if not result.lead_score:
            score_result = score_conversation(
                sentiment=result.sentiment,
                emotion=result.emotion,
                claims=result.claims,
                transcript=result.transcript.get("full_text"),
            )
            result.lead_score = {
                "overall": score_result.overall,
                "category": score_result.category,
                "confidence": score_result.confidence,
                "explanation": score_result.explanation,
                "verified_reasons": score_result.verified_reasons,
                "components": score_result.components,
            }

        return result

    def _default_registry(self) -> StageRegistry:
        """Build a registry with default stage ordering."""
        from app.analysis.stages.speech_to_text import SpeechToTextStage
        from app.analysis.stages.sentiment_stage import SentimentStage
        from app.analysis.stages.emotion_stage import EmotionStage
        from app.analysis.stages.claim_extraction import ClaimExtractionStage
        from app.analysis.stages.rag_verification import RAGVerificationStage

        registry = StageRegistry()
        registry.register(SpeechToTextStage())
        registry.register(SentimentStage())
        registry.register(EmotionStage())
        registry.register(ClaimExtractionStage())
        registry.register(RAGVerificationStage())
        return registry
