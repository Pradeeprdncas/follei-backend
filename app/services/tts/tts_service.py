"""Public TTS service backed by the same provider as real-time voice."""

import asyncio

from app.analysis.pipelines.language_service import LanguageService
from app.analysis.services.streaming_tts_service import AudioChunk, get_tts_provider


class TTSService:
    def list_voices(self) -> list[str]:
        return ["default"]

    async def synthesize_async(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        language: str | None = None,
    ) -> AudioChunk:
        language = LanguageService.normalize(language or LanguageService.detect(text))
        return await get_tts_provider().synthesize(
            text, language, voice=voice, speed=speed
        )

    def synthesize(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        language: str | None = None,
    ) -> bytes:
        return asyncio.run(self.synthesize_async(text, voice, speed, language)).audio

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        language: str | None = None,
    ):
        chunk = await self.synthesize_async(text, voice, speed, language)
        yield chunk.audio

    @property
    def is_loaded(self) -> bool:
        return True


AVAILABLE_VOICES = ["default"]
_service: TTSService | None = None


def get_tts_service() -> TTSService:
    global _service
    if _service is None:
        _service = TTSService()
    return _service
