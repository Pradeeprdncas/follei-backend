"""Calendar MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.calendar.service import CalendarService
from mcp.calendar.tools import (
    CalendarCreateEventTool,
    CalendarUpdateEventTool,
    CalendarCancelEventTool,
    CalendarGetAvailabilityTool,
)
from mcp.monitoring.metrics import record_connector_health


class CalendarConnector(MCPConnector):
    """Calendar management connector supporting Google Calendar & Outlook Calendar."""

    def __init__(self, service: CalendarService) -> None:
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "create_event": CalendarCreateEventTool(self.service),
            "update_event": CalendarUpdateEventTool(self.service),
            "cancel_event": CalendarCancelEventTool(self.service),
            "get_availability": CalendarGetAvailabilityTool(self.service),
        }

    @property
    def name(self) -> str:
        return "calendar"

    async def connect(self) -> None:
        """Connection setup check."""
        pass

    async def disconnect(self) -> None:
        """Teardown method."""
        pass

    async def health_check(self) -> bool:
        """Returns True if the integration can communicate properly, False otherwise."""
        # Check if either provider is set up and healthy
        healthy = (self.service.google_auth is not None) or (self.service.outlook_auth is not None)
        record_connector_health(self.name, healthy)
        return healthy

    async def refresh_token(self) -> None:
        """Refreshes tokens on config providers."""
        if self.service.google_auth:
            await self.service.google_auth.refresh()
        if self.service.outlook_auth:
            await self.service.outlook_auth.refresh()

    def get_tools(self) -> List[MCPTool]:
        """Exposes calendar tool instances."""
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Routes execution to specific sub-tools."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Calendar connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
