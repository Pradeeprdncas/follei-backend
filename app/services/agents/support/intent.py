"""Lightweight rule-based intent classification for inbound support messages.

Not a duplicate of anything already wired: the dormant System 3-6
`app/services/ai/intent_classifier.py` and `app/services/rag/llm/intent_router.py`
are neither wired into any active pipeline nor in scope for this pass. This is
a small, self-contained classifier scoped to exactly what the Support worker
needs: catching an explicit human request before wasting a retrieval+LLM call.
"""

_HUMAN_REQUEST_PHRASES = (
    "speak to a human", "talk to a human", "speak to an agent", "talk to an agent",
    "real person", "human agent", "human support", "connect me to", "escalate",
    "speak with someone", "talk to someone", "customer service representative",
)
_COMPLAINT_PHRASES = (
    "not working", "broken", "terrible", "awful", "unacceptable", "frustrated",
    "angry", "disappointed", "worst", "want a refund", "want my money back",
    "cancel my", "furious", "complaint",
)


def classify_intent(text: str) -> str:
    """Return 'escalation_requested', 'complaint', or 'question'."""
    value = (text or "").lower()
    if any(phrase in value for phrase in _HUMAN_REQUEST_PHRASES):
        return "escalation_requested"
    if any(phrase in value for phrase in _COMPLAINT_PHRASES):
        return "complaint"
    return "question"
