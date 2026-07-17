"""ERP service orchestrating provider adapters."""
from typing import Any, Dict, List
from mcp.erp.adapters import ERPAdapter
from mcp.erp.adapters.sap import SAPAdapter
from mcp.erp.adapters.oracle import OracleAdapter
from mcp.erp.adapters.odoo import OdooAdapter
from mcp.erp.adapters.dynamics import DynamicsAdapter


class ERPService:
    """Delegates ERP commands to SAP, Oracle, Odoo, or Microsoft Dynamics adapters."""

    def __init__(self, provider: str, credentials: Dict[str, Any]) -> None:
        """Initializes the ERP Service with the correct adapter.

        Args:
            provider: ERP provider name ('sap', 'oracle', 'odoo', 'dynamics').
            credentials: Key-value credentials required for the adapter.
        """
        self.provider_name = provider.lower()
        self.adapter: ERPAdapter = self._resolve_adapter(self.provider_name, credentials)

    def _resolve_adapter(self, provider: str, credentials: Dict[str, Any]) -> ERPAdapter:
        if provider == "sap":
            return SAPAdapter(
                base_url=credentials["base_url"],
                username=credentials.get("username", ""),
                password=credentials.get("password", "")
            )
        elif provider == "oracle":
            return OracleAdapter(
                base_url=credentials["base_url"],
                token=credentials.get("token", "")
            )
        elif provider == "odoo":
            return OdooAdapter(
                url=credentials["url"],
                db=credentials.get("db", ""),
                username=credentials.get("username", ""),
                password=credentials.get("password", "")
            )
        elif provider == "dynamics":
            return DynamicsAdapter(
                resource=credentials["resource"],
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", "")
            )
        else:
            raise ValueError(f"Unsupported ERP provider '{provider}'")

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.create_customer(customer_data)

    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.update_customer(customer_id, customer_data)

    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        return await self.adapter.search_customer(query)

    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.create_invoice(invoice_data)

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        return await self.adapter.get_invoice(invoice_id)

    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.create_purchase_order(po_data)

    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        return await self.adapter.get_inventory(item_id)

    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        return await self.adapter.update_inventory(item_id, quantity)

    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.create_vendor(vendor_data)

    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.adapter.create_sales_order(order_data)
