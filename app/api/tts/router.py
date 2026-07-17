import io
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.services.tts.tts_service import get_tts_service, AVAILABLE_VOICES

router = APIRouter(prefix="/tts", tags=["TTS"])


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)
    voice: str = Field(default="Bruno")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


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
def synthesize(payload: SynthesizeRequest):
    _validate_voice(payload.voice)
    svc = get_tts_service()
    try:
        wav_bytes = svc.synthesize(text=payload.text, voice=payload.voice, speed=payload.speed)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return Response(content=wav_bytes, media_type="audio/wav")


@router.post("/stream")
async def synthesize_stream(payload: SynthesizeRequest):
    _validate_voice(payload.voice)
    svc = get_tts_service()
    try:
        async def generate():
            async for chunk in svc.synthesize_stream(text=payload.text, voice=payload.voice, speed=payload.speed):
                yield chunk
        return StreamingResponse(generate(), media_type="audio/wav")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
