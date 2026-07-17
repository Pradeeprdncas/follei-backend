"""Claim extraction pipeline stage — extracts business claims from analysis context.

Transforms raw analysis data into structured BusinessClaim objects
that can be verified by the RAG verification stage.
"""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from loguru import logger


class ClaimExtractionStage(AnalysisStage):
    """Extracts structured business claims from sentiment, emotion, and transcript.

    Each claim is a business-relevant assertion that will be RAG-verified.
    """

    @property
    def name(self) -> str:
        return "claim_extraction"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        claims = []

        # Claim 1: Sentiment-based
        if ctx.sentiment:
            sent_label = ctx.sentiment.get("overall", "neutral")
            sent_conf = ctx.sentiment.get("overall_confidence", 0.0)
            if sent_label == "negative" and sent_conf > 0.5:
                claims.append({
                    "claim": "Customer expressed negative sentiment during conversation",
                    "category": "objection",
                    "confidence": sent_conf,
                    "source": "sentiment",
                    "evidence": f"Overall sentiment: {sent_label} ({sent_conf:.2f})",
                })

        # Claim 2: Emotion-based
        if ctx.emotion:
            emo_label = ctx.emotion.get("overall", "neutral")
            emo_conf = ctx.emotion.get("overall_confidence", 0.0)
            if emo_label in ("angry", "sad") and emo_conf > 0.5:
                claims.append({
                    "claim": f"Customer displayed {emo_label} emotion during conversation",
                    "category": "objection",
                    "confidence": emo_conf,
                    "source": "emotion",
                    "evidence": f"Overall emotion: {emo_label} ({emo_conf:.2f})",
                })
            elif emo_label == "happy" and emo_conf > 0.5:
                claims.append({
                    "claim": "Customer displayed positive engagement",
                    "category": "engagement",
                    "confidence": emo_conf,
                    "source": "emotion",
                    "evidence": f"Overall emotion: {emo_label} ({emo_conf:.2f})",
                })

        # Claim 3: Transcript-based intent signals
        if ctx.transcript:
            text_lower = ctx.transcript.lower()
            pricing_keywords = {"price", "pricing", "cost", "how much", "subscription", "plan", "billing", "pay"}
            intent_keywords = {"interested", "looking for", "need", "want", "purchase", "buy", "evaluate"}
            timeline_keywords = {"when", "how soon", "timeline", "deadline", "by when", "urgent", "asap"}
            feature_keywords = {"feature", "capability", "integration", "api", "support", "works with"}

            if any(kw in text_lower for kw in pricing_keywords):
                claims.append({
                    "claim": "Customer discussed pricing or cost",
                    "category": "pricing",
                    "confidence": 0.7,
                    "source": "transcript",
                    "evidence": "Pricing-related keywords detected in transcript",
                })
            if any(kw in text_lower for kw in intent_keywords):
                claims.append({
                    "claim": "Customer expressed purchase intent",
                    "category": "intent",
                    "confidence": 0.6,
                    "source": "transcript",
                    "evidence": "Intent-related keywords detected in transcript",
                })
            if any(kw in text_lower for kw in timeline_keywords):
                claims.append({
                    "claim": "Customer discussed timeline or urgency",
                    "category": "timeline",
                    "confidence": 0.6,
                    "source": "transcript",
                    "evidence": "Timeline-related keywords detected in transcript",
                })
            if any(kw in text_lower for kw in feature_keywords):
                claims.append({
                    "claim": "Customer inquired about product features",
                    "category": "feature",
                    "confidence": 0.6,
                    "source": "transcript",
                    "evidence": "Feature-related keywords detected in transcript",
                })

        ctx.claims = claims
        logger.info(f"Claim extraction: {len(claims)} claims extracted")
        return ctx
