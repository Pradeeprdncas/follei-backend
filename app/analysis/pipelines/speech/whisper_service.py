from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from app.analysis.speech.provider import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)


@dataclass
class WhisperService:
    model_name: str = "base"
    language: str | None = None
    model: object | None = None
    use_vad: bool = True

    def initialize(self):
        if self.model is not None:
            return
        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError("openai-whisper is required for speech-to-text") from exc
        self.model = whisper.load_model(self.model_name)
        logger.info("Loaded Whisper %s model", self.model_name)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return self.transcribe_with_language(audio, sample_rate)["text"]

    def transcribe_with_segments(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        raw = self._transcribe_raw(audio, sample_rate)
        segments = []
        for seg in raw.get("segments", []):
            segments.append(TranscriptionSegment(
                start_sec=float(seg.get("start", 0)),
                end_sec=float(seg.get("end", 0)),
                text=str(seg.get("text", "")).strip(),
                confidence=float(seg.get("avg_logprob", 0)) if seg.get("avg_logprob") is not None else 1.0,
            ))
        return TranscriptionResult(segments=segments)

    def transcribe_with_language(self, audio: np.ndarray, sample_rate: int = 16000) -> dict[str, str]:
        result = self._transcribe_raw(audio, sample_rate)
        return {
            "text": str(result.get("text", "")).strip(),
            "language": str(result.get("language") or self.language or "en").split("-")[0],
        }

    def _transcribe_raw(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        if sample_rate != 16000:
            raise ValueError("WhisperService expects 16kHz preprocessed audio")
        if self.model is None:
            self.initialize()
        use_fp16 = False
        try:
            import torch
            use_fp16 = torch.cuda.is_available()
        except ImportError:
            use_fp16 = False
        return self.model.transcribe(
            audio.astype("float32"),
            fp16=use_fp16,
            language=self.language if self.language not in (None, "", "auto") else None,
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            beam_size=3,
            best_of=3,
            no_speech_threshold=0.45,
            compression_ratio_threshold=2.0,
            logprob_threshold=-1.0,
            verbose=False,
            initial_prompt=(
                "This is a phone conversation. "
                "Transcribe exactly what is spoken. "
                "Do NOT add any text the speaker did not say."
            ),
        )
