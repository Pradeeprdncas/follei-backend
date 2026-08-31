"""IndicF5 inference server implementing Follei's internal TTS contract."""
from __future__ import annotations

import asyncio
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from transformers import AutoModel


MODEL_ID = os.getenv("TTS_MODEL_ID", "ai4bharat/IndicF5")
MODEL_REVISION = os.getenv("TTS_MODEL_REVISION", "").strip()
REFERENCE_AUDIO = Path(os.getenv("TTS_REFERENCE_AUDIO", ""))
REFERENCE_TEXT = os.getenv("TTS_REFERENCE_TEXT", "").strip()
API_KEY = os.getenv("TTS_API_KEY", "").strip()


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: str = "ta"
    model: str = "tamil-prosody-v1"
    accent: str = "spoken-tamil"
    prosody_profile: str = "conversational"
    voice_profile: str | None = None
    speed: float = Field(default=1.0, ge=0.75, le=1.25)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MODEL_REVISION:
        raise RuntimeError("TTS_MODEL_REVISION must pin an exact Hugging Face commit")
    if not REFERENCE_AUDIO.is_file() or not REFERENCE_TEXT:
        raise RuntimeError("TTS_REFERENCE_AUDIO and TTS_REFERENCE_TEXT are required")
    app.state.model = AutoModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        trust_remote_code=True,
    )
    app.state.generation_lock = asyncio.Lock()
    yield
    app.state.model = None


app = FastAPI(title="Follei Tamil TTS", lifespan=lifespan)


def _generate(model, text: str) -> bytes:
    audio = np.asarray(
        model(text, ref_audio_path=str(REFERENCE_AUDIO), ref_text=REFERENCE_TEXT),
        dtype=np.float32,
    )
    if np.max(np.abs(audio), initial=0) > 1.0:
        audio = audio / 32768.0
    destination = io.BytesIO()
    sf.write(destination, audio, 24000, format="WAV", subtype="PCM_16")
    return destination.getvalue()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_ID, "revision": MODEL_REVISION}


@app.post("/synthesize")
async def synthesize(
    payload: SynthesisRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid TTS service token")
    if payload.language.split("-", 1)[0].lower() != "ta":
        raise HTTPException(status_code=400, detail="this model server currently supports Tamil only")
    if payload.voice_profile:
        raise HTTPException(
            status_code=400,
            detail="named voice profiles are not enabled in the zero-shot baseline server",
        )
    async with app.state.generation_lock:
        wav = await asyncio.to_thread(_generate, app.state.model, payload.text)
    return Response(wav, media_type="audio/wav", headers={"X-TTS-Provider": "indicf5"})
