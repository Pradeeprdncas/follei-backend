from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np

from app.analysis.speech.provider import TranscriptionResult, TranscriptionSegment
from app.analysis.pipelines.speech.transcript_cleaner import clean_transcript, filter_segments

logger = logging.getLogger(__name__)


@dataclass
class FasterWhisperService:
    model_name: str = "base"
    language: str | None = None
    model: object | None = None
    device: str = "auto"
    compute_type: str = "default"
    use_vad: bool = True
    use_chunking: bool = True
    chunk_max_seconds: int = 30

    def initialize(self):
        if self.model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is required for speech-to-text") from exc

        device = self.device
        compute_type = self.compute_type
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

        self.model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=4,
            num_workers=2,
        )
        logger.info("Loaded Faster-Whisper %s on %s (%s)", self.model_name, device, compute_type)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        result = self.transcribe_with_segments(audio, sample_rate)
        return result.full_text

    def transcribe_with_segments(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> TranscriptionResult:
        if self.model is None:
            self.initialize()

        language = self.language
        if language in (None, "", "auto"):
            language = None

        # For long audio, split on silence and transcribe each chunk
        if self.use_chunking and len(audio) > sample_rate * self.chunk_max_seconds:
            return self._transcribe_long(audio, sample_rate, language)

        return self._transcribe_chunk(audio, sample_rate, language, start_offset=0.0)

    def _transcribe_long(
        self, audio: np.ndarray, sample_rate: int, language: str | None
    ) -> TranscriptionResult:
        from app.analysis.pipelines.speech.audio_chunker import split_on_silence

        chunks = split_on_silence(
            audio,
            sample_rate=sample_rate,
            max_chunk_len_ms=self.chunk_max_seconds * 1000,
            silence_thresh=0.02,
            min_silence_len_ms=400,
            keep_silence_ms=200,
        )
        logger.info("Split audio into %d chunks for transcription", len(chunks))

        all_segments: List[TranscriptionSegment] = []
        for chunk_start, chunk_end, chunk_audio in chunks:
            offset_sec = chunk_start / sample_rate
            result = self._transcribe_chunk(chunk_audio, sample_rate, language, offset_sec)
            all_segments.extend(result.segments)

        if not all_segments:
            return TranscriptionResult(segments=[])

        result = TranscriptionResult(segments=all_segments)
        result = filter_segments(result)
        return result

    def _transcribe_chunk(
        self, audio: np.ndarray, sample_rate: int, language: str | None, start_offset: float
    ) -> TranscriptionResult:
        vad_params = dict(
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=100,
            speech_pad_ms=400,
        ) if self.use_vad else None

        segments, info = self.model.transcribe(
            audio.astype(np.float32),
            language=language,
            task="transcribe",
            beam_size=3,
            best_of=3,
            temperature=[0.0, 0.2],
            condition_on_previous_text=False,
            no_speech_threshold=0.45,
            compression_ratio_threshold=2.0,
            log_prob_threshold=-1.0,
            vad_filter=self.use_vad,
            vad_parameters=vad_params,
            initial_prompt=(
                "This is a phone conversation. "
                "Transcribe exactly what is spoken. "
                "Do NOT add any text the speaker did not say."
            ),
        )

        tx_segments: List[TranscriptionSegment] = []
        for seg in segments:
            tx_segments.append(TranscriptionSegment(
                start_sec=round(seg.start + start_offset, 3),
                end_sec=round(seg.end + start_offset, 3),
                text=seg.text.strip(),
                confidence=round(seg.avg_logprob, 4) if seg.avg_logprob else 0.0,
            ))

        result = TranscriptionResult(segments=tx_segments)
        result = filter_segments(result)
        return result
