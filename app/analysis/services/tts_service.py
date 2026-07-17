from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from app.analysis.pipelines.language_service import LanguageService
from app.analysis.services.elevenlabs_service import ElevenLabsService
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


class TTSService:
    def __init__(self, voice_id: str | None = None, output_dir: str | None = None):
        self._voice_id = voice_id or _settings.ELEVENLABS_VOICE_ID
        self._output_dir = Path(output_dir or _settings.TTS_OUTPUT_DIR)
        self._language_service = LanguageService()

    def resolve_voice(self, user_text: str = "", user_language: str = "") -> str:
        detected = self._language_service.detect(user_text) if user_text else user_language
        is_tamil = "tam" in detected.lower() or detected.lower() in ("ta", "tamil")
        if is_tamil and _settings.ELEVENLABS_MALE_VOICE_ID:
            return _settings.ELEVENLABS_MALE_VOICE_ID
        if not is_tamil and _settings.ELEVENLABS_FEMALE_VOICE_ID:
            return _settings.ELEVENLABS_FEMALE_VOICE_ID
        return self._voice_id

    def synthesize(
        self,
        text: str,
        user_text: str = "",
        user_language: str = "en",
    ) -> dict:
        if not text:
            return {"status": "empty", "audio_path": None}
        voice_id = self.resolve_voice(user_text, user_language)
        ts_path = self._output_dir / f"response_{hash(text) & 0xFFFFFFFF:08x}.mp3"
        return ElevenLabsService.synthesize(
            text=text,
            destination=ts_path,
            language=user_language or "en",
            voice_id=voice_id,
        )

    def audio_to_numpy(self, audio_path: str) -> np.ndarray:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("soundfile is required to load audio") from exc
        audio, _ = sf.read(audio_path, always_2d=False)
        return np.asarray(audio, dtype=np.float32)
