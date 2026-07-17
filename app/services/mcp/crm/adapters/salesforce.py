"""Salesforce CRM API Adapter."""
from typing import Any, Dict, List
import httpx
from mcp.base.exceptions import ConnectorError
from mcp.crm.adapters import CRMAdapter


class SalesforceAdapter(CRMAdapter):
    """Integrates with Salesforce Enterprise CRM via OAuth2 access token and instance URL."""

    def __init__(self, instance_url: str, access_token: str) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = "v57.0"
        self.base_url = f"{self.instance_url}/services/data/{self.api_version}"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/sobjects/Lead"
        # Salesforce Lead requires Company and LastName
        payload = {
            "FirstName": lead_data["first_name"],
            "LastName": lead_data["last_name"],
            "Email": lead_data["email"],
            "Company": lead_data.get("company") or "Individual",
        }
        if lead_data.get("phone"):
            payload["Phone"] = lead_data["phone"]
            
        payload.update(lead_data.get("custom_properties", {}))
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Salesforce create_lead failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Salesforce create_lead HTTP error: {e}") from e

    async def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/sobjects/Lead/{lead_id}"
        # Convert properties to SF names
        payload = {}
        for k, v in lead_data.items():
            if k == "first_name":
                payload["FirstName"] = v
            elif k == "last_name":
                payload["LastName"] = v
            elif k == "company":
                payload["Company"] = v
            elif k == "phone":
                payload["Phone"] = v
            else:
                payload[k] = v
                
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            # Salesforce PATCH returns 204 No Content on success
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Salesforce update_lead failed ({res.status_code}): {res.text}")
            return {"id": lead_id, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Salesforce update_lead HTTP error: {e}") from e

    async def search_contact(self, query: str) -> List[Dict[str, Any]]:
        # SOSL Find search query
        sosl_query = f"FIND '{query}' IN ALL FIELDS RETURNING Contact(Id, FirstName, LastName, Email, Phone)"
        url = f"{self.base_url}/search"
        params = {"q": sosl_query}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, params=params, headers=self._get_headers())
            if res.status_code != 200:
                raise ConnectorError(f"Salesforce search failed ({res.status_code}): {res.text}")
            # Salesforce returns searchResults as list
            return res.json().get("searchRecords", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Salesforce search HTTP error: {e}") from e

    async def create_opportunity(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/sobjects/Opportunity"
        # Salesforce Opportunity requires Name, StageName, CloseDate
        payload = {
            "Name": opp_data["name"],
            "StageName": opp_data["stage"],
            "CloseDate": opp_data["close_date"],
            "Amount": opp_data["amount"],
        }
        payload.update(opp_data.get("custom_properties", {}))
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Salesforce create_opportunity failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Salesforce create_opportunity HTTP error: {e}") from e

    async def update_opportunity(self, opp_id: str, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/sobjects/Opportunity/{opp_id}"
        payload = {}
        for k, v in opp_data.items():
            if k == "name":
                payload["Name"] = v
            elif k == "stage":
                payload["StageName"] = v
            elif k == "close_date":
                payload["CloseDate"] = v
            elif k == "amount":
                payload["Amount"] = v
            else:
                payload[k] = v
                
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
            if res.status_code not in (200, 204):
                raise ConnectorError(f"Salesforce update_opportunity failed ({res.status_code}): {res.text}")
            return {"id": opp_id, "status": "updated"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ConnectorError(f"Salesforce update_opportunity HTTP error: {e}") from e
