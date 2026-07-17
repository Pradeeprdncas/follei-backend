"""Text-to-Speech service — delegates to ElevenLabs (replaces KittenTTS)."""

import re
from pathlib import Path

from app.config.settings import get_settings
from app.analysis.services.elevenlabs_service import ElevenLabsService
from app.analysis.services.tts_service import TTSService as AnalysisTTSService

VOICE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{20,}$")


class TTSService:
    def __init__(self) -> None:
        self._delegate = AnalysisTTSService()

    def list_voices(self) -> list[str]:
        return ["default"]

    def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> bytes:
        settings = get_settings()
        voice_id = settings.ELEVENLABS_VOICE_ID
        if voice and VOICE_ID_PATTERN.match(voice):
            voice_id = voice
        ts_path = Path(settings.TTS_OUTPUT_DIR) / f"response_{hash(text) & 0xFFFFFFFF:08x}.mp3"
        ElevenLabsService.synthesize(text=text, destination=ts_path, voice_id=voice_id)
        return ts_path.read_bytes()

    @property
    def is_loaded(self) -> bool:
        return ElevenLabsService.configured()


AVAILABLE_VOICES = ["default"]
_service: TTSService | None = None


def get_tts_service() -> TTSService:
    global _service
    if _service is None:
        _service = TTSService()
    return _service
