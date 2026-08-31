"""Conservative text cleanup before Tamil/Tanglish speech synthesis."""
from __future__ import annotations

import re


_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?])")
_MISSING_SPACE_AFTER_PUNCTUATION = re.compile(r"([,.;:!?])(?=[^\s\d])")
_WHITESPACE = re.compile(r"\s+")


def normalize_for_speech(text: str, language: str) -> str:
    """Clean model output without translating code-mixed English terms.

    Romanized-Tamil transliteration belongs in the Tamil model server, where a
    contextual normalizer can distinguish Tamil words from names and business
    vocabulary. The API sends both this cleaned text and the language metadata.
    """
    value = (text or "").replace("\u200b", "").replace("…", ".")
    value = value.replace("—", ", ").replace("–", "-")
    value = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", value)
    value = _MISSING_SPACE_AFTER_PUNCTUATION.sub(r"\1 ", value)
    value = _WHITESPACE.sub(" ", value).strip()
    return value
