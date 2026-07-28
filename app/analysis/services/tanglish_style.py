"""Conversational Tanglish guidance derived from the approved vocabulary list.

The source PDF contains 1,511 English words commonly mixed into everyday
Tamil. Sending the complete list on every LLM turn would waste context and
latency, so Follei supplies a small topic-relevant subset instead.
"""
from __future__ import annotations

import re

_COMMON = (
    "actually", "okay", "sure", "check", "confirm", "update", "clear",
    "ready", "important", "quick", "simple", "better", "issue", "solution",
)
_TOPIC_VOCABULARY = {
    "money": (
        "budget", "price", "pricing", "cost", "payment", "discount", "plan",
        "subscription", "invoice",
    ),
    "sales": (
        "sales", "customer", "lead", "demo", "deal", "campaign", "follow-up",
        "target", "revenue",
    ),
    "time": (
        "timeline", "deadline", "schedule", "week", "today", "tomorrow",
        "meeting", "reminder",
    ),
    "technology": (
        "admin", "profile", "data", "platform", "automatic", "app", "website",
        "link", "module", "notification", "settings",
    ),
    "education": (
        "instructor", "class", "title", "topic", "chapter", "module", "join",
        "button", "student", "training",
    ),
    "business": (
        "owner", "company", "business", "decision", "process", "team",
        "support", "project", "requirement",
    ),
}
_TOPIC_PATTERNS = {
    "money": re.compile(r"\b(budget|price|pricing|cost|pay|payment|10k|discount)\b", re.I),
    "sales": re.compile(r"\b(sales|lead|demo|deal|campaign|customer|revenue)\b", re.I),
    "time": re.compile(r"\b(week|day|today|tomorrow|timeline|deadline|urgent|fast)\b", re.I),
    "technology": re.compile(r"\b(admin|profile|data|platform|app|website|link|module|settings)\b", re.I),
    "education": re.compile(r"\b(instructor|class|chapter|topic|student|course|join)\b", re.I),
    "business": re.compile(r"\b(owner|company|business|decision|team|process|support)\b", re.I),
}


def vocabulary_for(text: str, *, limit: int = 32) -> tuple[str, ...]:
    """Return a compact, de-duplicated vocabulary relevant to this utterance."""
    lowered = text.lower()
    all_topic_words = tuple(word for group in _TOPIC_VOCABULARY.values() for word in group)
    # Terms the caller actually used matter more than generic style words.
    words = [word for word in all_topic_words if word in lowered]
    words.extend(_COMMON)
    for topic, pattern in _TOPIC_PATTERNS.items():
        if pattern.search(text):
            words.extend(_TOPIC_VOCABULARY[topic])
    if len(words) == len(_COMMON):
        words.extend(_TOPIC_VOCABULARY["business"])
    return tuple(dict.fromkeys(words))[:limit]


def prompt_instruction(user_text: str) -> str:
    vocabulary = ", ".join(vocabulary_for(user_text))
    return (
        " Respond in natural day-to-day Tanglish: use conversational Tamil in Tamil script "
        "and mix familiar English words in Latin script where a Tamil speaker normally would. "
        "Do not use formal, literary, or fully translated Tamil. Do not transliterate the whole "
        "reply into Latin letters. Keep Tamil grammar and connecting words in every sentence; "
        "at least half of the reply should remain in Tamil script. Match this style: "
        "'Okay, உங்க budget 10Kன்னு clear. One week timeline-க்கு practical setup plan check பண்ணலாம்.' "
        "Use these approved everyday English terms when they fit "
        f"naturally: {vocabulary}. Use at most three short sentences and roughly 70 words; "
        "give the direct answer first and ask only one useful follow-up question. "
        "Return plain text only: no Markdown, asterisks, headings, bullet symbols, or emoji."
    )
