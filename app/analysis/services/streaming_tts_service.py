"""Token-to-phrase buffering and swappable speech synthesis providers."""
from __future__ import annotations

import asyncio
import base64
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.analysis.services.elevenlabs_service import ElevenLabsService
from app.config.settings import get_settings
from app.analysis.services.speech_text_normalizer import normalize_for_speech

_settings = get_settings()
_BOUNDARY = re.compile(r"[.!?]\s$|[,;:]\s$")


@dataclass(slots=True)
class AudioChunk:
    audio: bytes
    format: str = "mp3"
    provider: str = "unknown"

    @property
    def media_type(self) -> str:
        return {
            "mp3": "audio/mpeg",
            "mpeg": "audio/mpeg",
            "wav": "audio/wav",
            "wave": "audio/wav",
            "ogg": "audio/ogg",
            "webm": "audio/webm",
        }.get(self.format.lower(), f"audio/{self.format.lower()}")


class TTSProvider(Protocol):
    async def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice: str = "default",
        speed: float = 1.0,
    ) -> AudioChunk: ...


class ConfiguredTTSProvider:
    """Current ElevenLabs/gTTS adapter behind a stable streaming interface."""

    async def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice: str = "default",
        speed: float = 1.0,
    ) -> AudioChunk:
        text = normalize_for_speech(text, language)
        destination = Path(_settings.TTS_OUTPUT_DIR) / f"stream_{uuid.uuid4().hex}.mp3"
        voice_id = _settings.ELEVENLABS_TAMIL_VOICE_ID if language == "ta" else None
        try:
            metadata = await asyncio.to_thread(
                ElevenLabsService.synthesize,
                text=text,
                destination=destination,
                language=language,
                voice_id=voice_id,
            )
            return AudioChunk(
                audio=destination.read_bytes(),
                provider=str(metadata.get("engine", "elevenlabs")),
            )
        finally:
            destination.unlink(missing_ok=True)


class FolleiModelTTSProvider:
    """Adapter for a dedicated Tamil acoustic/prosody model server."""

    async def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice: str = "default",
        speed: float = 1.0,
    ) -> AudioChunk:
        voice_profile = _settings.FOLLEI_TTS_VOICE_PROFILE.strip()
        if voice_profile and not _settings.FOLLEI_TTS_VOICE_CONSENT_CONFIRMED:
            raise RuntimeError(
                "FOLLEI_TTS_VOICE_CONSENT_CONFIRMED must be true before using a voice profile"
            )
        payload = {
            "text": normalize_for_speech(text, language),
            "language": language,
            "model": _settings.FOLLEI_TTS_MODEL,
            "accent": _settings.FOLLEI_TTS_ACCENT,
            "prosody_profile": _settings.FOLLEI_TTS_PROSODY_PROFILE,
            "voice_profile": voice_profile or None,
            "speed": speed,
        }
        headers = {}
        if _settings.FOLLEI_TTS_API_KEY:
            headers["Authorization"] = f"Bearer {_settings.FOLLEI_TTS_API_KEY}"
        async with httpx.AsyncClient(timeout=_settings.FOLLEI_TTS_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{_settings.FOLLEI_TTS_BASE_URL.rstrip('/')}/synthesize",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type.startswith("audio/"):
            return AudioChunk(
                audio=response.content,
                format=content_type.removeprefix("audio/"),
                provider="follei",
            )
        result = response.json()
        return AudioChunk(
            audio=base64.b64decode(result["audio_base64"], validate=True),
            format=str(result.get("format", "wav")),
            provider="follei",
        )


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
    if _settings.TTS_PROVIDER.strip().lower() == "follei":
        return FolleiModelTTSProvider()
    return ConfiguredTTSProvider()
