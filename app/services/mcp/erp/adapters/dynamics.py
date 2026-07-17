"""Microsoft Dynamics 365 Finance REST API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.erp.adapters import ERPAdapter


class DynamicsAdapter(ERPAdapter):
    """Integrates with Microsoft Dynamics 365 Finance & Operations OData endpoints."""

    def __init__(self, resource: str, client_id: str = "", client_secret: str = "") -> None:
        self.resource = resource.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = ""

    async def _get_valid_token(self) -> str:
        """Retrieves azure active directory bearer token."""
        if self.access_token:
            return self.access_token

        url = "https://login.microsoftonline.com/common/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "resource": self.resource
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, data=payload)
            if res.status_code != 200:
                raise ConnectorError(f"Dynamics AAD auth failed ({res.status_code}): {res.text}")
            self.access_token = res.json()["access_token"]
            return self.access_token
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics token auth HTTP error: {e}") from e

    async def _get_headers(self) -> Dict[str, str]:
        token = await self._get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/CustomersV3"
        payload = {
            "CustomerAccount": customer_data.get("account_number") or "CUST-NEW",
            "OrganizationName": customer_data["name"]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Dynamics create_customer failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics create_customer HTTP error: {e}") from e

    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/CustomersV3(CustomerAccount='{customer_id}')"
        payload = {"OrganizationName": customer_data.get("name")}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Dynamics update_customer failed ({res.status_code}): {res.text}")
            return {"customer_id": customer_id, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics update_customer HTTP error: {e}") from e

    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.resource}/data/CustomersV3"
        params = {"$filter": f"substringof('{query}', OrganizationName)"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=await self._get_headers(), params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Dynamics search_customer failed ({res.status_code}): {res.text}")
            return res.json().get("value", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics search_customer HTTP error: {e}") from e

    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/SalesInvoiceHeaders"
        payload = {
            "InvoiceNumber": invoice_data.get("invoice_number", "INV-NEW"),
            "OrderingCustomerAccountNumber": invoice_data["customer_id"]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Dynamics create_invoice failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics create_invoice HTTP error: {e}") from e

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        url = f"{self.resource}/data/SalesInvoiceHeaders(InvoiceNumber='{invoice_id}')"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=await self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"Dynamics get_invoice failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics get_invoice HTTP error: {e}") from e

    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/PurchaseOrderHeaders"
        payload = {
            "PurchaseOrderNumber": po_data.get("po_number", "PO-NEW"),
            "VendorAccountNumber": po_data["vendor_id"]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Dynamics create_purchase_order failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics create_purchase_order HTTP error: {e}") from e

    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        url = f"{self.resource}/data/InventoryStagingProducts(ItemNumber='{item_id}')"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=await self._get_headers())
            if res.status_code == 404:
                return {"item_id": item_id, "quantity": 0.0, "status": "Not Found"}
            if res.status_code != 200:
                raise ConnectorError(f"Dynamics get_inventory failed ({res.status_code}): {res.text}")
            data = res.json()
            return {"item_id": item_id, "quantity": float(data.get("OnHandQuantity", 0.0))}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics get_inventory HTTP error: {e}") from e

    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        url = f"{self.resource}/data/InventoryStagingProducts(ItemNumber='{item_id}')"
        payload = {"OnHandQuantity": quantity}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Dynamics update_inventory failed ({res.status_code}): {res.text}")
            return {"item_id": item_id, "quantity": quantity, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics update_inventory HTTP error: {e}") from e

    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/Vendors"
        payload = {
            "VendorAccountNumber": vendor_data.get("vendor_number") or "VEND-NEW",
            "VendorName": vendor_data["name"]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Dynamics create_vendor failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics create_vendor HTTP error: {e}") from e

    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.resource}/data/SalesOrderHeaders"
        payload = {
            "SalesOrderNumber": order_data.get("order_number", "SO-NEW"),
            "OrderingCustomerAccountNumber": order_data["customer_id"]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=await self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Dynamics create_sales_order failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Dynamics create_sales_order HTTP error: {e}") from e
