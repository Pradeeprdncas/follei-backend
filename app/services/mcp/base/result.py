"""MCP execution result model."""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MCPResult(BaseModel):
    """Standardized response return type for all MCP tool executions."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
