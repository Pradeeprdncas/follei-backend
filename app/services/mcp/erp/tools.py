"""ERP MCP Tool implementations."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.erp.service import ERPService
from mcp.erp.schemas import (
    CREATE_CUSTOMER_SCHEMA,
    UPDATE_CUSTOMER_SCHEMA,
    SEARCH_CUSTOMER_SCHEMA,
    CREATE_INVOICE_SCHEMA,
    GET_INVOICE_SCHEMA,
    CREATE_PURCHASE_ORDER_SCHEMA,
    GET_INVENTORY_SCHEMA,
    UPDATE_INVENTORY_SCHEMA,
    CREATE_VENDOR_SCHEMA,
    CREATE_SALES_ORDER_SCHEMA,
)


class ERPCreateCustomerTool(MCPTool):
    """Creates customer."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_create_customer"

    @property
    def description(self) -> str:
        return "Creates a new customer record in the enterprise ERP database."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_CUSTOMER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_customer(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPUpdateCustomerTool(MCPTool):
    """Updates customer."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_update_customer"

    @property
    def description(self) -> str:
        return "Updates customer details in the ERP system."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return UPDATE_CUSTOMER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.update_customer(
                customer_id=params["customer_id"],
                customer_data=params["customer_data"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPSearchCustomerTool(MCPTool):
    """Searches customers."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_search_customer"

    @property
    def description(self) -> str:
        return "Searches customers in the ERP workspace matching name query."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEARCH_CUSTOMER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.search_customer(
                query=params["query"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPCreateInvoiceTool(MCPTool):
    """Creates invoice."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_create_invoice"

    @property
    def description(self) -> str:
        return "Generates a customer billing invoice in the ERP platform."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_INVOICE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_invoice(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPGetInvoiceTool(MCPTool):
    """Gets invoice."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_get_invoice"

    @property
    def description(self) -> str:
        return "Retrieves invoice metadata details from ERP database."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_INVOICE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_invoice(
                invoice_id=params["invoice_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPCreatePurchaseOrderTool(MCPTool):
    """Creates purchase order."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_create_purchase_order"

    @property
    def description(self) -> str:
        return "Submits a new purchase order for supplier/materials stock replenish."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_PURCHASE_ORDER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_purchase_order(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPGetInventoryTool(MCPTool):
    """Gets inventory."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_get_inventory"

    @property
    def description(self) -> str:
        return "Queries active stock balance balance numbers in ERP inventory warehouse."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_INVENTORY_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_inventory(
                item_id=params["item_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPUpdateInventoryTool(MCPTool):
    """Updates inventory count."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_update_inventory"

    @property
    def description(self) -> str:
        return "Sets stock balances count level adjustments for a product item in the ERP."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return UPDATE_INVENTORY_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.update_inventory(
                item_id=params["item_id"],
                quantity=params["quantity"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPCreateVendorTool(MCPTool):
    """Creates vendor."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_create_vendor"

    @property
    def description(self) -> str:
        return "Creates a new vendor/supplier profile record in the ERP."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_VENDOR_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_vendor(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class ERPCreateSalesOrderTool(MCPTool):
    """Creates sales order."""

    def __init__(self, service: ERPService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "erp_create_sales_order"

    @property
    def description(self) -> str:
        return "Generates a new customer sales order in the ERP system."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_SALES_ORDER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_sales_order(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
