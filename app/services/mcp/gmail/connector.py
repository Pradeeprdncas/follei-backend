"""Gmail MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.gmail.auth import GmailAuth
from mcp.gmail.service import GmailService
from mcp.gmail.tools import (
    GmailSendEmailTool,
    GmailReplyEmailTool,
    GmailSearchEmailTool,
    GmailReadThreadTool,
)
from mcp.monitoring.metrics import record_connector_health


class GmailConnector(MCPConnector):
    """Google Workspace Gmail integration connector."""

    def __init__(self, auth: GmailAuth) -> None:
        self.auth = auth
        self.service = GmailService(auth)
        
        # Instantiate tools
        self._tools: Dict[str, MCPTool] = {
            "send_email": GmailSendEmailTool(self.service),
            "reply_email": GmailReplyEmailTool(self.service),
            "search_email": GmailSearchEmailTool(self.service),
            "read_thread": GmailReadThreadTool(self.service),
        }

    @property
    def name(self) -> str:
        return "gmail"

    async def connect(self) -> None:
        """Verifies connection by refreshing the token and performing a health check."""
        await self.auth.get_valid_token()
        is_healthy = await self.health_check()
        if not is_healthy:
            raise RuntimeError("Gmail connection health check failed.")

    async def disconnect(self) -> None:
        """Closes any sessions. (HTTPX handles connection pools automatically)."""
        pass

    async def health_check(self) -> bool:
        """Verifies connection health by fetching the user profile endpoint."""
        try:
            # Refresh token to ensure validity
            token = await self.auth.get_valid_token()
            import httpx
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    headers=headers
                )
            healthy = res.status_code == 200
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Programmatically refreshes Google API access token."""
        await self.auth.refresh()

    def get_tools(self) -> List[MCPTool]:
        """Exposes the Gmail tool instances."""
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Executes a tool owned by this connector."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Gmail connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
