"""Standardized Result Types - Common contracts for all AI operations.

Every loader returns these exact types. No strings, no dicts, no surprises.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class GenerationResult:
    """Standard result from text generation models."""
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"  # "stop", "length", "error"
    latency_ms: float = 0.0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_success(self) -> bool:
        return self.finish_reason != "error" and len(self.text) > 0
    
    @property
    def is_empty(self) -> bool:
        return not self.text or self.text.strip() in ("", "?", ".")


@dataclass
class EmbeddingResult:
    """Standard result from embedding models."""
    embedding: List[float]
    prompt_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RerankResult:
    """Standard result from reranking models."""
    documents: List[str]
    scores: List[float]
    query: str = ""
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Standard result from classification models."""
    primary_intent: str
    confidence: float
    all_intents: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Standard result from verification models."""
    is_correct: bool
    confidence: float
    explanation: str = ""
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanResult:
    """Standard result from planning models."""
    plan: List[str]
    reasoning: str = ""
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryRewriteResult:
    """Standard result from query rewriting models."""
    original_query: str
    rewritten_query: str
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SummaryResult:
    """Standard result from summarization models."""
    summary: str
    original_length: int = 0
    summary_length: int = 0
    compression_ratio: float = 0.0
    model: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_success(self) -> bool:
        return len(self.summary) > 0