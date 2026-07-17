"""CRM MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.crm.service import CRMService
from mcp.crm.tools import (
    CRMCreateLeadTool,
    CRMUpdateLeadTool,
    CRMSearchContactTool,
    CRMCreateOpportunityTool,
    CRMUpdateOpportunityTool,
)
from mcp.monitoring.metrics import record_connector_health


class CRMConnector(MCPConnector):
    """Routing connector linking to HubSpot, Salesforce, or Zoho adapters via CRMService."""

    def __init__(self, service: CRMService) -> None:
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "create_lead": CRMCreateLeadTool(self.service),
            "update_lead": CRMUpdateLeadTool(self.service),
            "search_contact": CRMSearchContactTool(self.service),
            "create_opportunity": CRMCreateOpportunityTool(self.service),
            "update_opportunity": CRMUpdateOpportunityTool(self.service),
        }

    @property
    def name(self) -> str:
        return f"crm_{self.service.provider_name}"

    async def connect(self) -> None:
        """Connector setup validation."""
        # Simple health check as connection check
        is_healthy = await self.health_check()
        if not is_healthy:
            raise RuntimeError(f"CRM Connector '{self.name}' health check failed.")

    async def disconnect(self) -> None:
        """Teardown method."""
        pass

    async def health_check(self) -> bool:
        """Performs simple ping check (searches for a mock query or hits provider root)."""
        try:
            # We run a lightweight search query to verify API credentials work
            await self.service.search_contact("health-check-dummy@follei.com")
            record_connector_health(self.name, True)
            return True
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Refreshes credentials if applicable (e.g. if the adapter supports token refresh)."""
        pass

    def get_tools(self) -> List[MCPTool]:
        """Lists CRM tools."""
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Routes execution to CRM subtools."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"CRM connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
