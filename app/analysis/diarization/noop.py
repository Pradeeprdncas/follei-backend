"""No-op diarization provider — returns a single "unknown" speaker.

Used when no diarization model is deployed. Complies with the provider
interface so the pipeline never needs to know diarization is missing.
"""
from app.analysis.diarization.provider import DiarizerProvider, DiarizationResult, SpeakerSegment


class NoOpDiarizer(DiarizerProvider):
    async def diarize(self, audio_bytes: bytes, sample_rate: int = 16000) -> DiarizationResult:
        # Assume 10 seconds default — caller must specify duration if known
        return DiarizationResult(speakers=[
            SpeakerSegment(start_sec=0.0, end_sec=0.0, speaker="unknown"),
        ])

    async def diarize_file(self, audio_path: str) -> DiarizationResult:
        return DiarizationResult(speakers=[
            SpeakerSegment(start_sec=0.0, end_sec=0.0, speaker="unknown"),
        ])
