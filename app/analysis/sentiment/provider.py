"""Sentiment analysis provider interface.

Supports text-based sentiment (TF-IDF, transformer classifiers, etc.)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SentimentSegment:
    start_sec: float
    end_sec: float
    label: str
    confidence: float
    text: str | None = None
    scores: dict[str, float] | None = None


@dataclass
class SentimentResult:
    segments: list[SentimentSegment] = field(default_factory=list)

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


class SentimentProvider(ABC):
    @abstractmethod
    async def analyze(self, text: str) -> SentimentResult:
        ...

    @abstractmethod
    async def analyze_segments(
        self, segments: list[tuple[float, float, str]]
    ) -> SentimentResult:
        ...
