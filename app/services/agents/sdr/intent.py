"""Rule-based intent classification for the SDR worker.

Mirrors app/services/agents/support/intent.py's deliberately-small,
self-contained substring approach — scoped to exactly the branches the SDR
worker acts on (booking a meeting vs. discussing pricing vs. open discovery),
so a cheap classification can short-circuit the meeting-booking path before
spending a retrieval+LLM call.
"""

_MEETING_PHRASES = (
    "book a meeting", "schedule a meeting", "set up a meeting", "set up a call",
    "book a call", "schedule a call", "schedule a demo", "book a demo",
    "set up a demo", "arrange a call", "arrange a meeting", "let's meet",
    "can we meet", "hop on a call", "jump on a call", "calendar", "available to talk",
)
_PRICING_PHRASES = (
    "pricing", "price", "cost", "how much", "quote", "budget", "plans",
    "subscription", "per month", "per year", "discount",
)


def classify_sdr_intent(text: str) -> str:
    """Return 'wants_meeting', 'asking_about_pricing', or 'general_discovery'."""
    value = (text or "").lower()
    if any(phrase in value for phrase in _MEETING_PHRASES):
        return "wants_meeting"
    if any(phrase in value for phrase in _PRICING_PHRASES):
        return "asking_about_pricing"
    return "general_discovery"
