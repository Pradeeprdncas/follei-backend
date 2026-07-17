"""Intent router — maps 2-axis classifier output to IntentMode for generator.

No longer does its own classification. Consumes the 4-mode RoutingMode
from classifier.py and maps to the old IntentMode enum for backward compat
with generator.py, prompts, and chat.py pipeline.
"""
from enum import Enum
from dataclasses import dataclass

from app.services.rag.classifier import ClassificationResult, RoutingMode


class IntentMode(str, Enum):
    GENERAL_KNOWLEDGE = "general"
    COMPANY_KNOWLEDGE = "knowledge"
    REASONING = "reasoning"
    HYBRID = "hybrid"


@dataclass
class IntentResult:
    mode: IntentMode
    confidence: float
    reason: str


_ROUTING_MODE_TO_INTENT = {
    RoutingMode.RETRIEVE_ONLY: IntentMode.COMPANY_KNOWLEDGE,
    RoutingMode.REASON_ONLY: IntentMode.GENERAL_KNOWLEDGE,
    RoutingMode.RETRIEVE_THEN_REASON: IntentMode.REASONING,
    RoutingMode.HYBRID: IntentMode.HYBRID,
}


def resolve_mode(cls: ClassificationResult) -> IntentMode:
    """Map 2-axis RoutingMode to backward-compatible IntentMode."""
    return _ROUTING_MODE_TO_INTENT.get(cls.mode, IntentMode.COMPANY_KNOWLEDGE)


def classify_intent(question: str, retrieval_score: float = 0.0) -> IntentResult:
    """Legacy wrapper — delegates to classifier, then maps to IntentMode.

    Kept for backward compat with chat.py pipeline. Prefer calling
    classifier.classify() directly, then resolve_mode().
    """
    from app.services.rag.classifier import get_query_classifier
    cls_result = get_query_classifier().classify(question)
    intent_mode = resolve_mode(cls_result)
    return IntentResult(
        mode=intent_mode,
        confidence=cls_result.confidence,
        reason=cls_result.reason,
    )
