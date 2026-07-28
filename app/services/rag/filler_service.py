"""Fast, contextual fillers used only when real answer audio is late."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pricing", re.compile(r"\b(price|pricing|budget|cost|payment|discount|10k)\b", re.I)),
    ("timeline", re.compile(r"\b(timeline|deadline|week|day|urgent|fast|delivery)\b", re.I)),
    ("demo", re.compile(r"\b(demo|meeting|call|schedule|appointment)\b", re.I)),
    ("technical", re.compile(r"\b(issue|error|integration|api|website|app|module|button)\b", re.I)),
    ("information", re.compile(r"\b(data|detail|information|profile|feature|plan|follei)\b", re.I)),
)

_TEMPLATES = {
    "en": {
        "pricing": ("Sure, I’m checking the best pricing fit.", "Okay, let me match that with your budget."),
        "timeline": ("Got it, I’m checking a practical timeline.", "Sure, let me work out the fastest realistic plan."),
        "demo": ("Absolutely, I’m checking the next demo option.", "Sure, let me line up the right next step."),
        "technical": ("Got it, I’m checking that setup now.", "Okay, let me look into that issue."),
        "information": ("Sure, I’m pulling the relevant details.", "Got it, let me get the useful information together."),
        "general": ("Sure, one moment.", "Got it, I’m checking that now.", "Okay, let me work that out."),
    },
    "ta": {
        "pricing": (
            "Sure, உங்க budget-க்கு சரியான pricing fit என்னன்னு check பண்றேன்.",
            "Okay, budget மற்றும் plan options-ஐ quick-ah compare பண்றேன்.",
        ),
        "timeline": (
            "Got it, உங்க timeline-க்கு fastest practical plan என்னன்னு check பண்றேன்.",
            "Sure, ஒரு week-க்குள்ள என்ன possibleன்னு quick-ah பார்க்கிறேன்.",
        ),
        "demo": (
            "Absolutely, demo அல்லது meeting-க்கு next available option check பண்றேன்.",
            "Sure, சரியான next step மற்றும் schedule-ஐ பார்க்கிறேன்.",
        ),
        "technical": (
            "Got it, அந்த issue மற்றும் setup-ஐ quick-ah check பண்றேன்.",
            "Okay, integration side-ல என்ன fix வேணும்னு பார்க்கிறேன்.",
        ),
        "information": (
            "Sure, relevant data மற்றும் details-ஐ quick-ah எடுத்துக்கறேன்.",
            "Got it, உங்களுக்கு useful ஆன information-ஐ check பண்றேன்.",
        ),
        "general": (
            "Sure, ஒரு second.",
            "Okay, இதை quick-ah check பண்றேன்.",
            "Got it, சரியான reply ready பண்றேன்.",
        ),
    },
    "hi": {
        "general": ("ठीक है, एक पल।", "ज़रूर, मैं अभी देख रहा हूँ।"),
    },
}
_last_choice: dict[tuple[str, str], int] = defaultdict(lambda: -1)


def _intent(text: str) -> str:
    for name, pattern in _INTENTS:
        if pattern.search(text):
            return name
    return "general"


async def generate_filler(
    user_text: str,
    language: str = "en",
    *,
    conversation_id: str | None = None,
) -> str:
    """Choose a relevant filler while avoiding the previous choice per session."""
    language_templates = _TEMPLATES.get(language, _TEMPLATES["en"])
    intent = _intent(user_text)
    templates = language_templates.get(intent) or language_templates["general"]
    key = (conversation_id or "global", language)
    digest = hashlib.blake2s(user_text.encode("utf-8"), digest_size=2).digest()
    choice = int.from_bytes(digest, "big") % len(templates)
    if len(templates) > 1 and choice == _last_choice[key]:
        choice = (choice + 1) % len(templates)
    _last_choice[key] = choice
    return templates[choice]
