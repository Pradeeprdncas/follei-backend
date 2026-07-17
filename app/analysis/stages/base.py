"""Abstract base for pipeline stages.

Each stage in the analysis pipeline is a self-contained unit that:
- Receives the current pipeline context
- Performs one transformation
- Returns updated context

Stages are registered by name and can be added/removed/reordered
via configuration without changing pipeline code.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """Mutable context passed through all pipeline stages.

    Each stage reads from and writes to this context.
    """
    tenant_id: str
    conversation_id: str | None = None
    audio_bytes: bytes | None = None
    audio_path: str | None = None
    transcript: str | None = None
    segments: list[dict] | None = None
    sentiment: dict | None = None
    emotion: dict | None = None
    fusion: dict | None = None
    lead_score: dict | None = None
    claims: list[dict] | None = None
    verification: list[dict] | None = None
    summary: str | None = None
    speakers: list[dict] | None = None
    duration_seconds: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalysisStage(ABC):
    """A single pluggable stage in the conversation analysis pipeline."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique stage name used for registry lookups."""
        ...

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Execute this stage. Mutates and returns the context."""
        ...

    @property
    def enabled(self) -> bool:
        """Override to conditionally disable this stage via config."""
        return True
