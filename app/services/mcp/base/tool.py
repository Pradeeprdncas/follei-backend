"""Abstract base class for MCP Tools."""
from abc import ABC, abstractmethod
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult


class MCPTool(ABC):
    """Abstract Base Class representing a single executable system action (Tool)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique lookup identifier for the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed functional description for LLMs to understand usage requirements."""
        pass

    @property
    @abstractmethod
    def capability(self) -> MCPCapability:
        """The capability classification this tool falls under."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema dictionary representing required and optional inputs."""
        pass

    @property
    @abstractmethod
    def output_schema(self) -> Dict[str, Any]:
        """JSON Schema dictionary representing output formats."""
        pass

    @abstractmethod
    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        """Asynchronously executes the tool action.

        Args:
            context: Execution context containing headers/tracing/permissions.
            params: Dictionary containing schema-validated execution arguments.

        Returns:
            MCPResult detailing success, error message, and response payloads.
        """
        pass
