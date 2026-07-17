"""WhatsApp MCP Connector implementation."""
from typing import Any, Dict, List
import httpx
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.whatsapp.service import WhatsAppService
from mcp.whatsapp.tools import (
    WhatsAppSendMessageTool,
    WhatsAppSendTemplateTool,
    WhatsAppSendMediaTool,
    WhatsAppGetConversationTool,
)
from mcp.monitoring.metrics import record_connector_health


class WhatsAppConnector(MCPConnector):
    """WhatsApp integration connector."""

    def __init__(self, service: WhatsAppService) -> None:
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "whatsapp_send_message": WhatsAppSendMessageTool(self.service),
            "whatsapp_send_template": WhatsAppSendTemplateTool(self.service),
            "whatsapp_send_media": WhatsAppSendMediaTool(self.service),
            "whatsapp_get_conversation": WhatsAppGetConversationTool(self.service),
        }

    @property
    def name(self) -> str:
        return "whatsapp"

    async def connect(self) -> None:
        """Verifies API connectivity via health check."""
        is_healthy = await self.health_check()
        if not is_healthy:
            raise RuntimeError("WhatsApp connection health check failed.")

    async def disconnect(self) -> None:
        """Teardown method."""
        pass

    async def health_check(self) -> bool:
        """Verifies access token validation by querying WhatsApp business profile details."""
        try:
            url = f"https://graph.facebook.com/v17.0/{self.service.phone_number_id}"
            headers = {"Authorization": f"Bearer {self.service.access_token}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url, headers=headers)
            healthy = res.status_code == 200
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """No-op. Permanent System User tokens do not support refresh endpoints directly."""
        pass

    def get_tools(self) -> List[MCPTool]:
        """Exposes WhatsApp tool instances."""
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Routes execution to sub-tools."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"WhatsApp connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
