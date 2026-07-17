"""Slack MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.slack.service import SlackService
from mcp.slack.tools import (
    SlackSendMessageTool,
    SlackListChannelsTool,
    SlackGetChannelMessagesTool,
    SlackCreateChannelTool,
    SlackInviteUserTool,
    SlackGetUserInfoTool,
    SlackSearchMessagesTool,
    SlackUploadFileTool,
    SlackScheduleMessageTool,
)
from mcp.monitoring.metrics import record_connector_health


class SlackConnector(MCPConnector):
    """Integrates Slack platform operations into the MCP framework."""

    def __init__(self, service: SlackService) -> None:
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "slack_send_message": SlackSendMessageTool(self.service),
            "slack_list_channels": SlackListChannelsTool(self.service),
            "slack_get_channel_messages": SlackGetChannelMessagesTool(self.service),
            "slack_create_channel": SlackCreateChannelTool(self.service),
            "slack_invite_user": SlackInviteUserTool(self.service),
            "slack_get_user_info": SlackGetUserInfoTool(self.service),
            "slack_search_messages": SlackSearchMessagesTool(self.service),
            "slack_upload_file": SlackUploadFileTool(self.service),
            "slack_schedule_message": SlackScheduleMessageTool(self.service),
        }

    @property
    def name(self) -> str:
        return "slack"

    async def connect(self) -> None:
        """Verifies access validity and performs connection checks."""
        is_healthy = await self.health_check()
        if not is_healthy:
            # We log warning but don't strictly throw if testing or running locally with fallback
            logger_msg = "Slack connector health check failed."
            from loguru import logger
            logger.warning(logger_msg)

    async def disconnect(self) -> None:
        """Closes Slack connection sessions."""
        pass

    async def health_check(self) -> bool:
        """Checks API reachability."""
        try:
            # Under slack-sdk, if initialized, check auth.test
            if self.service.client:
                res = await self.service.client.auth_test()
                healthy = res.get("ok", False)
            else:
                healthy = False
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Refreshes Slack credentials (not applicable for bot tokens)."""
        pass

    def get_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Slack connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
