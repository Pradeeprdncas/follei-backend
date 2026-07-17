"""MCP execution context."""
from typing import Dict, List, Any
from pydantic import BaseModel, Field


class MCPContext(BaseModel):
    """Execution context passed through the tool pipeline for auditing and routing."""

    organization_id: str
    user_id: str
    agent_id: str
    permissions: List[str] = Field(default_factory=list)
    request_id: str
    trace_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
