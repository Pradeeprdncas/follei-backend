"""Oracle NetSuite ERP REST API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.erp.adapters import ERPAdapter


class OracleAdapter(ERPAdapter):
    """Integrates with Oracle NetSuite REST web services."""

    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/customer"
        payload = {"companyName": customer_data["name"], "email": customer_data.get("email")}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Oracle create_customer failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle create_customer HTTP error: {e}") from e

    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/customer/{customer_id}"
        payload = {"companyName": customer_data.get("name")}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Oracle update_customer failed ({res.status_code}): {res.text}")
            return {"customer_id": customer_id, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle update_customer HTTP error: {e}") from e

    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/record/v1/customer"
        params = {"q": f"companyName CONTAINS '{query}'"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Oracle search_customer failed ({res.status_code}): {res.text}")
            return res.json().get("items", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle search_customer HTTP error: {e}") from e

    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/invoice"
        payload = {
            "entity": {"id": invoice_data["customer_id"]},
            "item": {
                "items": [
                    {
                        "amount": invoice_data.get("amount", 0.0),
                        "description": "Invoice line charge"
                    }
                ]
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Oracle create_invoice failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle create_invoice HTTP error: {e}") from e

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/invoice/{invoice_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"Oracle get_invoice failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle get_invoice HTTP error: {e}") from e

    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/purchaseOrder"
        payload = {
            "entity": {"id": po_data["vendor_id"]},
            "item": {
                "items": [
                    {
                        "item": {"id": po_data.get("item_id")},
                        "quantity": po_data.get("quantity", 1.0)
                    }
                ]
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Oracle create_purchase_order failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle create_purchase_order HTTP error: {e}") from e

    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/inventoryItem/{item_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
            if res.status_code == 404:
                return {"item_id": item_id, "quantity": 0.0, "status": "Not Found"}
            if res.status_code != 200:
                raise ConnectorError(f"Oracle get_inventory failed ({res.status_code}): {res.text}")
            data = res.json()
            return {"item_id": item_id, "quantity": float(data.get("quantityOnHand", 0.0))}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle get_inventory HTTP error: {e}") from e

    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/inventoryItem/{item_id}"
        payload = {"quantityOnHand": quantity}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Oracle update_inventory failed ({res.status_code}): {res.text}")
            return {"item_id": item_id, "quantity": quantity, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle update_inventory HTTP error: {e}") from e

    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/vendor"
        payload = {"companyName": vendor_data["name"]}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Oracle create_vendor failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle create_vendor HTTP error: {e}") from e

    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/record/v1/salesOrder"
        payload = {
            "entity": {"id": order_data["customer_id"]},
            "item": {
                "items": [
                    {
                        "item": {"id": order_data.get("item_id")},
                        "quantity": order_data.get("quantity", 1.0)
                    }
                ]
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Oracle create_sales_order failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Oracle create_sales_order HTTP error: {e}") from e
