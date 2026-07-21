"""Rule-based intent classification for the Sales Executive worker.

Same small substring approach as app/services/agents/support/intent.py and
sdr/intent.py, scoped to the branches the Sales worker acts on: handling an
objection, being asked for a proposal/quote, or a signal the deal is ready to
close — anything else is treated as ongoing product discussion.
"""

_OBJECTION_PHRASES = (
    "too expensive", "too much", "can't afford", "cannot afford", "out of budget",
    "not sure", "not convinced", "competitor", "already using", "concern",
    "worried", "hesitant", "why should", "what about", "but ", "however",
    "not interested", "think about it",
)
_PROPOSAL_PHRASES = (
    "proposal", "send me a quote", "send a quote", "put together", "in writing",
    "paperwork", "contract", "send over the details", "formal offer", "sow",
    "statement of work",
)
_CLOSING_PHRASES = (
    "ready to buy", "let's do it", "sign up", "get started", "move forward",
    "go ahead", "where do i sign", "purchase", "close the deal", "send the invoice",
)


def classify_sales_intent(text: str) -> str:
    """Return 'closing', 'wants_proposal', 'objection', or 'product_discussion'."""
    value = (text or "").lower()
    if any(phrase in value for phrase in _CLOSING_PHRASES):
        return "closing"
    if any(phrase in value for phrase in _PROPOSAL_PHRASES):
        return "wants_proposal"
    if any(phrase in value for phrase in _OBJECTION_PHRASES):
        return "objection"
    return "product_discussion"
