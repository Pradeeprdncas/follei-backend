from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.services.tts.tts_service import get_tts_service, AVAILABLE_VOICES

router = APIRouter(prefix="/tts", tags=["TTS"])


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)
    voice: str = Field(default="default")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str | None = Field(default=None, pattern=r"^[a-zA-Z]{2,3}(?:[-_][a-zA-Z]{2})?$")


class VoicesResponse(BaseModel):
    voices: list[str]


def _validate_voice(voice: str):
    if voice not in AVAILABLE_VOICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown voice '{voice}'. Available: {AVAILABLE_VOICES}",
        )


@router.get("/voices", response_model=VoicesResponse)
def list_voices():
    svc = get_tts_service()
    return VoicesResponse(voices=svc.list_voices())


@router.post("/synthesize")
async def synthesize(payload: SynthesizeRequest):
    _validate_voice(payload.voice)
    svc = get_tts_service()
    try:
        chunk = await svc.synthesize_async(
            text=payload.text,
            voice=payload.voice,
            speed=payload.speed,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return Response(content=chunk.audio, media_type=chunk.media_type)


@router.post("/stream")
async def synthesize_stream(payload: SynthesizeRequest):
    _validate_voice(payload.voice)
    svc = get_tts_service()
    try:
        chunk = await svc.synthesize_async(
            text=payload.text,
            voice=payload.voice,
            speed=payload.speed,
            language=payload.language,
        )

        async def generate():
            yield chunk.audio

        return StreamingResponse(generate(), media_type=chunk.media_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
