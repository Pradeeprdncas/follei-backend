"""Emotion detection provider interface.

Supports voice-based (CNN-MFCC, Wav2Vec2) and future video-based providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmotionSegment:
    start_sec: float
    end_sec: float
    label: str
    confidence: float
    probabilities: dict[str, float] | None = None


@dataclass
class EmotionResult:
    segments: list[EmotionSegment] = field(default_factory=list)

    @property
    def overall_label(self) -> str:
        if not self.segments:
            return "neutral"
        return max(self.segments, key=lambda s: s.confidence).label

    @property
    def overall_confidence(self) -> float:
        if not self.segments:
            return 0.0
        return max(s.confidence for s in self.segments)


class EmotionProvider(ABC):
    @abstractmethod
    async def recognize(self, audio_bytes: bytes, sample_rate: int = 16000) -> EmotionResult:
        ...

    @abstractmethod
    async def recognize_file(self, audio_path: str) -> EmotionResult:
        ...

    @property
    @abstractmethod
    def labels(self) -> list[str]:
        """Return the emotion labels this provider supports."""
        ...
