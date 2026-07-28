"""Token-to-phrase buffering and swappable speech synthesis providers."""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.analysis.services.elevenlabs_service import ElevenLabsService
from app.config.settings import get_settings

_settings = get_settings()
_BOUNDARY = re.compile(r"[.!?]\s$|[,;:]\s$")


@dataclass(slots=True)
class AudioChunk:
    audio: bytes
    format: str = "mp3"


class TTSProvider(Protocol):
    async def synthesize(self, text: str, language: str) -> AudioChunk: ...


class ConfiguredTTSProvider:
    """Current ElevenLabs/gTTS adapter behind a stable streaming interface."""

    async def synthesize(self, text: str, language: str) -> AudioChunk:
        destination = Path(_settings.TTS_OUTPUT_DIR) / f"stream_{uuid.uuid4().hex}.mp3"
        voice_id = _settings.ELEVENLABS_TAMIL_VOICE_ID if language == "ta" else None
        try:
            await asyncio.to_thread(
                ElevenLabsService.synthesize,
                text=text,
                destination=destination,
                language=language,
                voice_id=voice_id,
            )
            return AudioChunk(audio=destination.read_bytes())
        finally:
            destination.unlink(missing_ok=True)


class PhraseBuffer:
    """Turn arbitrary LLM tokens into natural TTS-sized phrases."""

    def __init__(self, *, min_chars: int = 28, max_chars: int = 90):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._text = ""

    def push(self, token: str) -> list[str]:
        self._text += token
        ready: list[str] = []
        while len(self._text) >= self.max_chars:
            split_at = max(
                self._text.rfind(mark, self.min_chars, self.max_chars)
                for mark in (" ", ", ", "; ", ": ")
            )
            if split_at < self.min_chars:
                split_at = self.max_chars
            ready.append(self._take(split_at + 1))
        if len(self._text) >= self.min_chars and _BOUNDARY.search(self._text):
            ready.append(self._take(len(self._text)))
        return [part for part in ready if part]

    def flush(self) -> str:
        return self._take(len(self._text))

    def _take(self, length: int) -> str:
        value = self._text[:length].strip()
        self._text = self._text[length:].lstrip()
        return value


def get_tts_provider() -> TTSProvider:
    return ConfiguredTTSProvider()
