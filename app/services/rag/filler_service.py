"""Immediate, query-aware filler for voice calls.

This deliberately avoids an LLM call: an SLM first-token delay would make the
filler late, defeating its purpose.  English technical words from the caller
are kept so the spoken Tamil sounds conversational rather than over-formal.
"""
import re


def _topic(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]*", text or "")
    return " ".join(words[:4]).strip()


async def generate_filler(user_text: str) -> str:
    """Return instant colloquial Tamil with the caller's technical keywords."""
    topic = _topic(user_text)
    if topic:
        return f"சரி, {topic} பற்றி பார்த்து சொல்றேன்."
    return "சரி, இதைப் பார்த்து சொல்றேன்."