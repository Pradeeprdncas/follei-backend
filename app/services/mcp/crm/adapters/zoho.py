"""Zoho CRM API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.crm.adapters import CRMAdapter


class ZohoAdapter(CRMAdapter):
    """Integrates with Zoho CRM via OAuth token authentication."""

    def __init__(self, access_token: str, base_url: str = "https://www.zohoapis.com/crm/v2") -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Zoho-oauthtoken {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/Leads"
        lead_properties = {
            "First_Name": lead_data["first_name"],
            "Last_Name": lead_data["last_name"],
            "Email": lead_data["email"],
            "Company": lead_data.get("company") or "Individual",
        }
        if lead_data.get("phone"):
            lead_properties["Phone"] = lead_data["phone"]
            
        lead_properties.update(lead_data.get("custom_properties", {}))
        
        payload = {"data": [lead_properties]}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Zoho create_lead failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Zoho create_lead HTTP error: {e}") from e

    async def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/Leads/{lead_id}"
        lead_properties = {"id": lead_id}
        for k, v in lead_data.items():
            if k == "first_name":
                lead_properties["First_Name"] = v
            elif k == "last_name":
                lead_properties["Last_Name"] = v
            elif k == "company":
                lead_properties["Company"] = v
            elif k == "phone":
                lead_properties["Phone"] = v
            else:
                lead_properties[k] = v
                
        payload = {"data": [lead_properties]}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.put(url, json=payload, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"Zoho update_lead failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Zoho update_lead HTTP error: {e}") from e

    async def search_contact(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/Contacts/search"
        # Search criteria or word search
        params = {"word": query}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, params=params, headers=self._get_headers())
            # Zoho search returns 204 No Content if no results match
            if res.status_code == 204:
                return []
            if res.status_code != 200:
                raise ConnectorError(f"Zoho search failed ({res.status_code}): {res.text}")
            return res.json().get("data", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Zoho search HTTP error: {e}") from e

    async def create_opportunity(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/Deals"
        properties = {
            "Deal_Name": opp_data["name"],
            "Stage": opp_data["stage"],
            "Closing_Date": opp_data["close_date"],
            "Amount": opp_data["amount"],
        }
        properties.update(opp_data.get("custom_properties", {}))
        
        payload = {"data": [properties]}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Zoho create_opportunity failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Zoho create_opportunity HTTP error: {e}") from e

    async def update_opportunity(self, opp_id: str, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/Deals/{opp_id}"
        properties = {"id": opp_id}
        for k, v in opp_data.items():
            if k == "name":
                properties["Deal_Name"] = v
            elif k == "stage":
                properties["Stage"] = v
            elif k == "close_date":
                properties["Closing_Date"] = v
            elif k == "amount":
                properties["Amount"] = v
            else:
                properties[k] = v
                
        payload = {"data": [properties]}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.put(url, json=payload, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"Zoho update_opportunity failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Zoho update_opportunity HTTP error: {e}") from e
