"""Microsoft Teams MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.teams.auth import TeamsAuth
from mcp.teams.service import TeamsService
from mcp.teams.tools import (
    TeamsSendMessageTool,
    TeamsListTeamsTool,
    TeamsListChannelsTool,
    TeamsGetMessagesTool,
    TeamsCreateChannelTool,
    TeamsAddMemberTool,
    TeamsScheduleMeetingTool,
)
from mcp.monitoring.metrics import record_connector_health


class TeamsConnector(MCPConnector):
    """Integrates Microsoft Teams collaboration features into the MCP framework."""

    def __init__(self, auth: TeamsAuth, service: TeamsService) -> None:
        self.auth = auth
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "teams_send_message": TeamsSendMessageTool(self.service),
            "teams_list_teams": TeamsListTeamsTool(self.service),
            "teams_list_channels": TeamsListChannelsTool(self.service),
            "teams_get_messages": TeamsGetMessagesTool(self.service),
            "teams_create_channel": TeamsCreateChannelTool(self.service),
            "teams_add_member": TeamsAddMemberTool(self.service),
            "teams_schedule_meeting": TeamsScheduleMeetingTool(self.service),
        }

    @property
    def name(self) -> str:
        return "teams"

    async def connect(self) -> None:
        """Verifies Graph API token validity and checks connection health."""
        await self.auth.get_valid_token()
        is_healthy = await self.health_check()
        if not is_healthy:
            from loguru import logger
            logger.warning("Microsoft Teams connector health check failed.")

    async def disconnect(self) -> None:
        """Closes Teams connection sessions."""
        pass

    async def health_check(self) -> bool:
        """Validates connection to Microsoft Graph by making a me call."""
        try:
            await self.auth.get_valid_token()
            import httpx
            headers = self.auth.get_auth_headers()
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
        """Triggers access token refresh."""
        await self.auth.refresh()

    def get_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Teams connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
