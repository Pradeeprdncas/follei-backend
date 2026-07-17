"""Abstract base class for MCP Connectors."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool


class MCPConnector(ABC):
    """Abstract Base Class representing an external service integrator (Connector)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier of the external system integration (e.g. 'gmail')."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establishes or verifies connection channel with the integration service."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully closes connections and releases resources."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if the integration can communicate properly, False otherwise."""
        pass

    @abstractmethod
    async def refresh_token(self) -> None:
        """Triggers manual or programmatic access token refresh if OAuth based."""
        pass

    @abstractmethod
    def get_tools(self) -> List[MCPTool]:
        """Lists all registered tools under this connector."""
        pass

    @abstractmethod
    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Directly executes a sub-tool managed by this connector.

        Args:
            tool_name: The name of the specific tool to execute.
            context: Context containing telemetry and security parameters.
            params: Parameters matching the sub-tool input schema.
        """
        pass
