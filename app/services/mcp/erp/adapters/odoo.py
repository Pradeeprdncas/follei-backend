"""Odoo ERP JSON-RPC Adapter."""
import random
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.erp.adapters import ERPAdapter


class OdooAdapter(ERPAdapter):
    """Integrates with Odoo ERP via JSON-RPC web API calls."""

    def __init__(self, url: str, db: str = "", username: str = "", password: str = "") -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.cookies = {}

    async def _authenticate(self, client: httpx.AsyncClient) -> None:
        """Authenticate user session with Odoo database and retrieve uid/cookies."""
        auth_url = f"{self.url}/jsonrpc"
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "login",
                "args": [self.db, self.username, self.password]
            },
            "id": random.randint(1, 100000)
        }
        
        try:
            res = await client.post(auth_url, json=payload)
            if res.status_code != 200:
                raise ConnectorError(f"Odoo auth failed ({res.status_code}): {res.text}")
            
            data = res.json()
            if "error" in data:
                raise ConnectorError(f"Odoo auth JSON-RPC error: {data['error']}")
                
            self.uid = data.get("result")
            if not self.uid:
                raise ConnectorError("Odoo login failed: Invalid credentials or database name.")
            self.cookies = dict(res.cookies)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Odoo authenticate HTTP error: {e}") from e

    async def _execute(self, model: str, method: str, args: List[Any], kwargs: Dict[str, Any] = None) -> Any:
        """Call standard Odoo models using call_kw object dispatcher."""
        url = f"{self.url}/jsonrpc"
        
        async with httpx.AsyncClient(timeout=15.0, cookies=self.cookies) as client:
            if not self.uid:
                await self._authenticate(client)
                
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [self.db, self.uid, self.password, model, method, args, kwargs or {}]
                },
                "id": random.randint(1, 100000)
            }
            
            try:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise ConnectorError(f"Odoo execute failed ({res.status_code}): {res.text}")
                
                data = res.json()
                if "error" in data:
                    raise ConnectorError(f"Odoo JSON-RPC method execution error: {data['error']}")
                return data.get("result")
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ConnectorError(f"Odoo execute_kw HTTP error: {e}") from e

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {"name": customer_data["name"], "email": customer_data.get("email"), "customer_rank": 1}
        res_id = await self._execute("res.partner", "create", [params])
        return {"id": res_id, "name": customer_data["name"]}

    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {"name": customer_data.get("name")}
        success = await self._execute("res.partner", "write", [[int(customer_id)], params])
        return {"customer_id": customer_id, "success": success}

    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        domain = [["name", "ilike", query]]
        fields = ["id", "name", "email"]
        results = await self._execute("res.partner", "search_read", [domain], {"fields": fields})
        return list(results)

    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "partner_id": int(invoice_data["customer_id"]),
            "move_type": "out_invoice",
            "invoice_line_ids": [
                (0, 0, {
                    "name": "Line charge item",
                    "price_unit": float(invoice_data.get("amount", 1.0)),
                    "quantity": 1.0
                })
            ]
        }
        res_id = await self._execute("account.move", "create", [params])
        return {"id": res_id}

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        fields = ["id", "name", "partner_id", "amount_total", "state"]
        results = await self._execute("account.move", "read", [[int(invoice_id)]], {"fields": fields})
        return dict(results[0]) if results else {}

    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "partner_id": int(po_data["vendor_id"]),
            "order_line": [
                (0, 0, {
                    "product_id": int(po_data["item_id"]),
                    "product_qty": float(po_data.get("quantity", 1.0)),
                    "price_unit": 10.0
                })
            ]
        }
        res_id = await self._execute("purchase.order", "create", [params])
        return {"id": res_id}

    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        fields = ["id", "name", "qty_available"]
        results = await self._execute("product.product", "read", [[int(item_id)]], {"fields": fields})
        if not results:
            return {"item_id": item_id, "quantity": 0.0, "status": "Not Found"}
        return {"item_id": item_id, "quantity": float(results[0].get("qty_available", 0.0))}

    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        # Odoo uses stock.quant to update stocks
        # For simplicity of REST adapter contract, write qty_available or trigger stock adjustment
        params = {"qty_available": quantity}
        # In odoo product template can write or stock.quant call.
        success = await self._execute("product.product", "write", [[int(item_id)], params])
        return {"item_id": item_id, "quantity": quantity, "success": success}

    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {"name": vendor_data["name"], "supplier_rank": 1}
        res_id = await self._execute("res.partner", "create", [params])
        return {"id": res_id, "name": vendor_data["name"]}

    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "partner_id": int(order_data["customer_id"]),
            "order_line": [
                (0, 0, {
                    "product_id": int(order_data["item_id"]),
                    "product_uom_qty": float(order_data.get("quantity", 1.0))
                })
            ]
        }
        res_id = await self._execute("sale.order", "create", [params])
        return {"id": res_id}
