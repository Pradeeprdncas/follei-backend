"""Stable context contract shared by chat and every AI worker."""
from typing import Any
from pydantic import BaseModel, Field


class AgentContextContract(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    customer_context: dict[str, Any] = Field(default_factory=dict)
    memory_evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    trust_policy: dict[str, int] = Field(default_factory=dict)
