"""Outlook MCP Connector implementation."""
from typing import Any, Dict, List
import httpx
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.outlook.auth import OutlookAuth
from mcp.outlook.service import OutlookService
from mcp.outlook.tools import (
    OutlookSendEmailTool,
    OutlookReplyEmailTool,
    OutlookReadEmailTool,
    OutlookCreateEventTool,
)
from mcp.monitoring.metrics import record_connector_health


class OutlookConnector(MCPConnector):
    """Microsoft Graph Outlook integration connector."""

    def __init__(self, auth: OutlookAuth) -> None:
        self.auth = auth
        self.service = OutlookService(auth)
        self._tools: Dict[str, MCPTool] = {
            "outlook_send_email": OutlookSendEmailTool(self.service),
            "outlook_reply_email": OutlookReplyEmailTool(self.service),
            "outlook_read_email": OutlookReadEmailTool(self.service),
            "outlook_create_event": OutlookCreateEventTool(self.service),
        }

    @property
    def name(self) -> str:
        return "outlook"

    async def connect(self) -> None:
        """Connects by obtaining a valid access token and verifying health."""
        await self.auth.get_valid_token()
        is_healthy = await self.health_check()
        if not is_healthy:
            raise RuntimeError("Outlook connection health check failed.")

    async def disconnect(self) -> None:
        """Resource teardown."""
        pass

    async def health_check(self) -> bool:
        """Performs a self-check request to Microsoft Graph user details endpoint."""
        try:
            token = await self.auth.get_valid_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers=headers
                )
            healthy = res.status_code == 200
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Refreshes the Microsoft Graph token."""
        await self.auth.refresh()

    def get_tools(self) -> List[MCPTool]:
        """Exposes Outlook tool instances."""
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Executes one of the managed tools."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Outlook connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
