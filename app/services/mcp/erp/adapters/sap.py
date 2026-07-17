"""SAP ERP OData REST API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.erp.adapters import ERPAdapter


class SAPAdapter(ERPAdapter):
    """Integrates with SAP S/4HANA OData APIs."""

    def __init__(self, base_url: str, username: str = "", password: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def _get_headers(self) -> Dict[str, str]:
        import base64
        headers = {"Content-Type": "application/json"}
        if self.username and self.password:
            user_pass = f"{self.username}:{self.password}"
            encoded = base64.b64encode(user_pass.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        return headers

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_BusinessPartner"
        payload = {
            "BusinessPartnerName": customer_data["name"],
            "BusinessPartnerGrouping": "BP01",
            "OrganizationBPName1": customer_data["name"],
            "CorrespondenceLanguage": "EN"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"SAP create_customer failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP create_customer HTTP error: {e}") from e

    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_BusinessPartner('{customer_id}')"
        payload = {"BusinessPartnerName": customer_data.get("name")}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"SAP update_customer failed ({res.status_code}): {res.text}")
            return {"customer_id": customer_id, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP update_customer HTTP error: {e}") from e

    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/A_BusinessPartner"
        params = {"$filter": f"substringof('{query}', BusinessPartnerName)"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
            if res.status_code != 200:
                raise ConnectorError(f"SAP search_customer failed ({res.status_code}): {res.text}")
            return res.json().get("d", {}).get("results", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP search_customer HTTP error: {e}") from e

    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_BillingDocument"
        payload = {
            "BillingDocumentType": "F2",
            "SoldToParty": invoice_data["customer_id"],
            "to_BillingDocumentItem": [
                {
                    "BillingDocumentItem": "10",
                    "SalesDocumentItemCategory": "TAN",
                    "BillingQuantity": str(invoice_data.get("amount", 1.0))
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"SAP create_invoice failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP create_invoice HTTP error: {e}") from e

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/A_BillingDocument('{invoice_id}')"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"SAP get_invoice failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP get_invoice HTTP error: {e}") from e

    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_PurchaseOrder"
        payload = {
            "PurchaseOrderType": "NB",
            "Supplier": po_data["vendor_id"],
            "to_PurchaseOrderItem": [
                {
                    "PurchaseOrderItem": "10",
                    "Material": po_data.get("item_id"),
                    "OrderQuantity": str(po_data.get("quantity", 1.0))
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"SAP create_purchase_order failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP create_purchase_order HTTP error: {e}") from e

    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/A_MaterialStock('{item_id}')"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
            if res.status_code == 404:
                return {"item_id": item_id, "quantity": 0.0, "status": "Not Found"}
            if res.status_code != 200:
                raise ConnectorError(f"SAP get_inventory failed ({res.status_code}): {res.text}")
            d = res.json().get("d", {})
            return {"item_id": item_id, "quantity": float(d.get("MatlWrhsStkQtyInOrdUoM", 0.0))}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP get_inventory HTTP error: {e}") from e

    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        url = f"{self.base_url}/A_MaterialStock('{item_id}')"
        payload = {"MatlWrhsStkQtyInOrdUoM": str(quantity)}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"SAP update_inventory failed ({res.status_code}): {res.text}")
            return {"item_id": item_id, "quantity": quantity, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP update_inventory HTTP error: {e}") from e

    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_Supplier"
        payload = {
            "SupplierName": vendor_data["name"],
            "BPGrouping": "BP01"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"SAP create_vendor failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP create_vendor HTTP error: {e}") from e

    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/A_SalesOrder"
        payload = {
            "SalesOrderType": "TA",
            "SoldToParty": order_data["customer_id"],
            "to_Item": [
                {
                    "SalesOrderItem": "10",
                    "Material": order_data.get("item_id"),
                    "RequestedQuantity": str(order_data.get("quantity", 1.0))
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"SAP create_sales_order failed ({res.status_code}): {res.text}")
            return res.json().get("d", res.json())
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"SAP create_sales_order HTTP error: {e}") from e
