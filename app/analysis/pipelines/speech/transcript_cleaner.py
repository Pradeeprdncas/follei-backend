from __future__ import annotations

import logging
import re
from typing import List

from app.analysis.speech.provider import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)

_HALLUCINATED_PHRASES: list[re.Pattern] = [
    re.compile(r"\b(like\sand\ssubscribe|subscribe\sto\smy\schannel|hit\sthe\slike|please\slike\sand|click\sthe\sbell\sicon)\b", re.IGNORECASE),
    re.compile(r"\b(thank\syou\sfor\swatching|thanks\sfor\swatching|don't\sforget\sto\slike|thanks\sfor\slistening)\b", re.IGNORECASE),
    re.compile(r"\b(music|background\smusic|♪|♫|upbeat\smusic)\b"),
    re.compile(r"\b(cc\sby\s|subtitles\sby|transcript\sby|captions\sby)\b", re.IGNORECASE),
    re.compile(r"\b(share\sthis\svideo|check\sout\smy\sother|follow\sme\son)\b", re.IGNORECASE),
]

_MIN_SEGMENT_CONFIDENCE = -2.5


def clean_transcript(transcript: str) -> str:
    text = transcript
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in _HALLUCINATED_PHRASES:
        text = pattern.sub("", text)
    text = re.sub(r"(\.\s*){3,}", ". ", text)
    text = re.sub(r"(\?\s*){3,}", "? ", text)
    text = re.sub(r"(!\s*){3,}", "! ", text)
    text = re.sub(r"\b(okay\s+){2,}", "okay ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b((i'm\s+sorry|i\sam\s+sorry)\s+){2,}", "I'm sorry ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(sorry\s+){3,}", "sorry ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(um\s+){2,}", "um ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(uh\s+){2,}", "uh ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_hallucinated_segment(segment: TranscriptionSegment) -> bool:
    if not segment.text.strip():
        return True
    if segment.confidence is not None and segment.confidence < _MIN_SEGMENT_CONFIDENCE:
        return True
    text = segment.text.lower().strip()
    if len(text.split()) <= 2 and text in ("okay", "sorry", "um", "uh", "hmm", "thank you", "thanks"):
        return True
    for pattern in _HALLUCINATED_PHRASES:
        if pattern.search(text):
            return True
    return False


def is_repetitive_text(text: str) -> bool:
    words = text.strip().split()
    if len(words) < 4:
        return False
    if len(words) <= 6:
        unique = len(set(words))
        if unique == 1:
            return True
        return False
    for repeat_count in range(2, max(3, len(words) // 3 + 1)):
        if len(words) % repeat_count == 0:
            chunk_size = len(words) // repeat_count
            base = words[:chunk_size]
            if all(words[i * chunk_size:(i + 1) * chunk_size] == base for i in range(1, repeat_count)):
                return True
    return False


def filter_segments(result: TranscriptionResult) -> TranscriptionResult:
    filtered: List[TranscriptionSegment] = []
    seen_texts: set[str] = set()

    for seg in result.segments:
        if is_hallucinated_segment(seg):
            logger.debug("Dropping hallucinated segment: %r", seg.text[:50])
            continue

        cleaned = clean_transcript(seg.text)
        if not cleaned:
            continue

        if is_repetitive_text(cleaned):
            logger.debug("Dropping repetitive segment: %r", cleaned[:60])
            continue

        seg.text = cleaned

        text_key = cleaned.lower().strip()
        # Deduplicate near-identical consecutive segments
        if seen_texts:
            last = next(reversed(list(seen_texts)))
            if _is_duplicate(text_key, last):
                logger.debug("Dropping duplicate segment: %r", cleaned[:60])
                continue

        seen_texts.add(text_key)
        filtered.append(seg)

    return TranscriptionResult(segments=filtered)


def _is_duplicate(a: str, b: str, threshold: float = 0.85) -> bool:
    if not a or not b:
        return False
    a_words = a.split()
    b_words = b.split()
    if abs(len(a_words) - len(b_words)) / max(len(a_words), len(b_words), 1) > 0.3:
        return False
    common = sum(1 for w in a_words if w in b_words)
    return common / max(len(a_words), len(b_words), 1) >= threshold
