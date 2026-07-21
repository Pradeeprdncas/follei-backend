from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.config.settings import get_settings

_settings = get_settings()


class ElevenLabsService:
    BASE_URL = "https://api.elevenlabs.io/v1"

    @classmethod
    def configured(cls) -> bool:
        return bool(_settings.ELEVENLABS_API_KEY.strip())

    @classmethod
    def _gtts_fallback(
        cls,
        text: str,
        destination: Path,
        language: str = "en",
    ) -> dict[str, Any]:
        """Free gTTS fallback when ElevenLabs is unavailable."""
        from gtts import gTTS

        _LANG_MAP = {
            "en": "en", "ta": "ta", "hi": "hi", "es": "es", "fr": "fr",
            "de": "de", "it": "it", "pt": "pt", "ja": "ja", "ko": "ko",
            "zh": "zh", "ar": "ar", "ru": "ru", "nl": "nl",
        }
        tts_lang = _LANG_MAP.get(language, "en")
        tts = gTTS(text=text, lang=tts_lang)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tts.save(str(destination))
        return {
            "engine": "gtts_fallback",
            "status": "ok",
            "language": tts_lang,
            "model": "gtts",
            "voice_id": "google-default",
            "audio_path": str(destination),
        }

    @classmethod
    def transcribe(cls, audio: np.ndarray, sample_rate: int = 16000) -> dict[str, Any]:
        if not cls.configured():
            raise RuntimeError("ELEVENLABS_API_KEY is not configured")
        wav_bytes = cls._wav_bytes(audio, sample_rate)
        with httpx.Client(timeout=_settings.ELEVENLABS_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{cls.BASE_URL}/speech-to-text",
                headers={"xi-api-key": _settings.ELEVENLABS_API_KEY},
                data={
                    "model_id": _settings.ELEVENLABS_STT_MODEL,
                    "tag_audio_events": "false",
                    **(
                        {"language_code": _settings.ELEVENLABS_STT_LANGUAGE}
                        if _settings.ELEVENLABS_STT_LANGUAGE.strip().lower() not in {"", "auto"}
                        else {}
                    ),
                },
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            )
            response.raise_for_status()
            payload = response.json()
        from app.analysis.pipelines.language_service import LanguageService
        return {
            "text": str(payload.get("text", "")).strip(),
            "language": LanguageService.normalize(payload.get("language_code")),
            "language_probability": payload.get("language_probability"),
            "provider": "elevenlabs",
            "model": _settings.ELEVENLABS_STT_MODEL,
        }

    @classmethod
    def synthesize(
        cls,
        text: str,
        destination: Path,
        language: str = "en",
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        if not cls.configured():
            return cls._gtts_fallback(text, destination, language)
        destination.parent.mkdir(parents=True, exist_ok=True)
        selected_voice_id = voice_id or _settings.ELEVENLABS_VOICE_ID
        url = f"{cls.BASE_URL}/text-to-speech/{selected_voice_id}"
        body: dict[str, Any] = {
            "text": text,
            "model_id": _settings.ELEVENLABS_TTS_MODEL,
        }
        params = {"output_format": _settings.ELEVENLABS_OUTPUT_FORMAT}
        try:
            with httpx.Client(timeout=_settings.ELEVENLABS_TIMEOUT_SECONDS) as client:
                response = client.post(
                    url,
                    params=params,
                    headers={"xi-api-key": _settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                    json=body,
                )
                if response.status_code in (401, 403, 429):
                    from loguru import logger
                    logger.warning(
                        "ElevenLabs TTS returned status={}, falling back to gTTS",
                        response.status_code,
                    )
                    return cls._gtts_fallback(text, destination, language)
                response.raise_for_status()
                destination.write_bytes(response.content)
        except httpx.HTTPStatusError as exc:
            from loguru import logger
            logger.warning(
                "ElevenLabs TTS HTTP error {}, falling back to gTTS: {}",
                exc.response.status_code,
                exc,
            )
            return cls._gtts_fallback(text, destination, language)
        except Exception as exc:
            from loguru import logger
            logger.warning("ElevenLabs TTS failed, falling back to gTTS: {}", exc)
            return cls._gtts_fallback(text, destination, language)
        return {
            "engine": "elevenlabs",
            "status": "ok",
            "language": language,
            "model": _settings.ELEVENLABS_TTS_MODEL,
            "voice_id": selected_voice_id,
            "audio_path": str(destination),
        }

    @staticmethod
    def _wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()
