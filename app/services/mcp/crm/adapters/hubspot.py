"""HubSpot CRM API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.crm.adapters import CRMAdapter


class HubSpotAdapter(CRMAdapter):
    """Integrates with HubSpot CRM via Bearer token authentication."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com/crm/v3"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/objects/contacts"
        properties = {
            "firstname": lead_data["first_name"],
            "lastname": lead_data["last_name"],
            "email": lead_data["email"],
        }
        if lead_data.get("company"):
            properties["company"] = lead_data["company"]
        if lead_data.get("phone"):
            properties["phone"] = lead_data["phone"]
            
        # Add custom properties
        properties.update(lead_data.get("custom_properties", {}))
        
        payload = {"properties": properties}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"HubSpot create_lead failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"HubSpot create_lead HTTP error: {e}") from e

    async def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/objects/contacts/{lead_id}"
        # Convert keys if present
        properties = {}
        for k, v in lead_data.items():
            if k == "first_name":
                properties["firstname"] = v
            elif k == "last_name":
                properties["lastname"] = v
            else:
                properties[k] = v
                
        payload = {"properties": properties}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"HubSpot update_lead failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"HubSpot update_lead HTTP error: {e}") from e

    async def search_contact(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/objects/contacts/search"
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "value": query,
                            "propertyName": "email",
                            "operator": "EQ",
                        }
                    ]
                }
            ]
        }
        # If it doesn't look like an email, we can try searching firstname or lastname
        if "@" not in query:
            payload["filterGroups"] = [
                {
                    "filters": [
                        {
                            "value": query,
                            "propertyName": "firstname",
                            "operator": "EQ",
                        }
                    ]
                },
                {
                    "filters": [
                        {
                            "value": query,
                            "propertyName": "lastname",
                            "operator": "EQ",
                        }
                    ]
                }
            ]
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"HubSpot search failed ({res.status_code}): {res.text}")
            return res.json().get("results", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"HubSpot search HTTP error: {e}") from e

    async def create_opportunity(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/objects/deals"
        properties = {
            "dealname": opp_data["name"],
            "dealstage": opp_data["stage"],
            "closedate": opp_data["close_date"],
            "amount": str(opp_data["amount"]),
        }
        properties.update(opp_data.get("custom_properties", {}))
        payload = {"properties": properties}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"HubSpot create_opportunity failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"HubSpot create_opportunity HTTP error: {e}") from e

    async def update_opportunity(self, opp_id: str, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/objects/deals/{opp_id}"
        # Convert stage/name keys
        properties = {}
        for k, v in opp_data.items():
            if k == "name":
                properties["dealname"] = v
            elif k == "stage":
                properties["dealstage"] = v
            elif k == "close_date":
                properties["closedate"] = v
            else:
                properties[k] = v
                
        payload = {"properties": properties}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"HubSpot update_opportunity failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"HubSpot update_opportunity HTTP error: {e}") from e
