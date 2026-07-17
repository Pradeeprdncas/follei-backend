"""ERP MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.erp.service import ERPService
from mcp.erp.tools import (
    ERPCreateCustomerTool,
    ERPUpdateCustomerTool,
    ERPSearchCustomerTool,
    ERPCreateInvoiceTool,
    ERPGetInvoiceTool,
    ERPCreatePurchaseOrderTool,
    ERPGetInventoryTool,
    ERPUpdateInventoryTool,
    ERPCreateVendorTool,
    ERPCreateSalesOrderTool,
)
from mcp.monitoring.metrics import record_connector_health


class ERPConnector(MCPConnector):
    """Integrates ERP (SAP/Oracle/Odoo/Dynamics) operations into the MCP framework."""

    def __init__(self, service: ERPService) -> None:
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "erp_create_customer": ERPCreateCustomerTool(self.service),
            "erp_update_customer": ERPUpdateCustomerTool(self.service),
            "erp_search_customer": ERPSearchCustomerTool(self.service),
            "erp_create_invoice": ERPCreateInvoiceTool(self.service),
            "erp_get_invoice": ERPGetInvoiceTool(self.service),
            "erp_create_purchase_order": ERPCreatePurchaseOrderTool(self.service),
            "erp_get_inventory": ERPGetInventoryTool(self.service),
            "erp_update_inventory": ERPUpdateInventoryTool(self.service),
            "erp_create_vendor": ERPCreateVendorTool(self.service),
            "erp_create_sales_order": ERPCreateSalesOrderTool(self.service),
        }

    @property
    def name(self) -> str:
        return f"erp_{self.service.provider_name}"

    async def connect(self) -> None:
        """Perifies connection configurations."""
        is_healthy = await self.health_check()
        if not is_healthy:
            from loguru import logger
            logger.warning(f"ERP connector '{self.name}' health check failed.")

    async def disconnect(self) -> None:
        """Closes connection sessions."""
        pass

    async def health_check(self) -> bool:
        """Verifies connector availability by querying a mock query or customer search."""
        try:
            # Basic query to verify endpoints
            res = await self.service.search_customer("health_check_test_query")
            healthy = isinstance(res, list)
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Refreshes connection credentials if supported by active adapter."""
        pass

    def get_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"ERP connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
