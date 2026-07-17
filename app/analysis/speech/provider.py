"""Speech-to-text provider interface.

All STT implementations (Whisper, Google Cloud STT, Azure STT, etc.)
must implement this interface. The pipeline accepts any provider via DI.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranscriptionSegment:
    start_sec: float
    end_sec: float
    text: str
    confidence: float = 1.0
    speaker: str | None = None


@dataclass
class TranscriptionResult:
    segments: list[TranscriptionSegment] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def duration_sec(self) -> float:
        return max((s.end_sec for s in self.segments), default=0.0)


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        ...

    @abstractmethod
    async def transcribe_file(self, audio_path: str) -> TranscriptionResult:
        ...
