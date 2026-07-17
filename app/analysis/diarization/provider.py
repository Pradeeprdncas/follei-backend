"""Speaker diarization provider interface.

Supports pyannote.audio, NVIDIA NeMo, and future diarization backends.
The NoOpProvider returns a single "unknown" speaker for all audio.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SpeakerSegment:
    start_sec: float
    end_sec: float
    speaker: str


@dataclass
class DiarizationResult:
    speakers: list[SpeakerSegment] = field(default_factory=list)

    @property
    def unique_speakers(self) -> list[str]:
        return sorted(set(s.speaker for s in self.speakers))

    @property
    def speaker_count(self) -> int:
        return len(self.unique_speakers)


class DiarizerProvider(ABC):
    @abstractmethod
    async def diarize(self, audio_bytes: bytes, sample_rate: int = 16000) -> DiarizationResult:
        ...

    @abstractmethod
    async def diarize_file(self, audio_path: str) -> DiarizationResult:
        ...
