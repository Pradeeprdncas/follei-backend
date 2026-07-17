"""CRM service orchestrating provider adapters."""
from typing import Any, Dict, List
from mcp.crm.adapters import CRMAdapter
from mcp.crm.adapters.hubspot import HubSpotAdapter
from mcp.crm.adapters.salesforce import SalesforceAdapter
from mcp.crm.adapters.zoho import ZohoAdapter


class CRMService:
    """Delegates CRM commands to HubSpot, Salesforce, or Zoho adapters."""

    def __init__(self, provider: str, credentials: Dict[str, Any]) -> None:
        """Initializes the CRM Service with the correct adapter.

        Args:
            provider: CRM provider name ('hubspot', 'salesforce', 'zoho').
            credentials: Key-value credentials required for the adapter.
        """
        self.provider_name = provider.lower()
        self.adapter: CRMAdapter = self._resolve_adapter(self.provider_name, credentials)

    def _resolve_adapter(self, provider: str, credentials: Dict[str, Any]) -> CRMAdapter:
        if provider == "hubspot":
            return HubSpotAdapter(api_key=credentials["api_key"])
        elif provider == "salesforce":
            return SalesforceAdapter(
                instance_url=credentials["instance_url"],
                access_token=credentials["access_token"],
            )
        elif provider == "zoho":
            return ZohoAdapter(
                access_token=credentials["access_token"],
                base_url=credentials.get("base_url", "https://www.zohoapis.com/crm/v2"),
            )
        else:
            raise ValueError(f"Unsupported CRM provider '{provider}'")

    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a lead in the active CRM."""
        return await self.adapter.create_lead(lead_data)

    async def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an existing lead."""
        return await self.adapter.update_lead(lead_id, lead_data)

    async def search_contact(self, query: str) -> List[Dict[str, Any]]:
        """Searches for contacts matching name/email."""
        return await self.adapter.search_contact(query)

    async def create_opportunity(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new opportunity/deal."""
        return await self.adapter.create_opportunity(opp_data)

    async def update_opportunity(self, opp_id: str, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an existing opportunity/deal."""
        return await self.adapter.update_opportunity(opp_id, opp_data)
