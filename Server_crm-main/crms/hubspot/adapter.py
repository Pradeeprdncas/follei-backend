"""
HubSpot CRM Adapter.
Implements the CRMAdapter interface, communicating with HubSpot via GenericClient.
"""
from typing import Any, Dict, List, Optional

from core.adapter import CRMAdapter
from crms.hubspot import endpoints
from crms.hubspot.mapper import HubSpotMapper
from models.schemas import (
    Company,
    CompanyCreate,
    CompanyUpdate,
    Contact,
    ContactCreate,
    ContactUpdate,
    Deal,
    DealCreate,
    DealUpdate,
)


class HubSpotAdapter(CRMAdapter):
    """
    Adapter to bind HubSpot API endpoints to standardized methods.
    """

    # --- CONTACTS ---

    async def get_contacts(self, limit: int = 100, after: Optional[str] = None) -> List[Contact]:
        params = {"limit": limit}
        if after:
            params["after"] = after
        res = await self.client.get(endpoints.CONTACTS, params=params)
        return HubSpotMapper.to_contacts_list(res)

    async def get_contact(self, contact_id: str) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        res = await self.client.get(endpoint)
        return HubSpotMapper.to_contact(res)

    async def search_contacts(self, filters: Dict[str, Any]) -> List[Contact]:
        # Simple translation of key-value dictionary into HubSpot's search DSL
        # e.g., {'email': 'test@test.com'} -> EQ filter
        hs_filters = []
        for key, val in filters.items():
            hs_filters.append({
                "propertyName": key,
                "operator": "EQ",
                "value": val
            })
            
        payload = {
            "filterGroups": [{"filters": hs_filters}]
        }
        res = await self.client.post(endpoints.CONTACT_SEARCH, json=payload)
        return HubSpotMapper.to_contacts_list(res)

    async def create_contact(self, contact: ContactCreate) -> Contact:
        payload = HubSpotMapper.from_contact_create(contact)
        res = await self.client.post(endpoints.CONTACTS, json=payload)
        return HubSpotMapper.to_contact(res)

    async def update_contact(self, contact_id: str, contact: ContactUpdate) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        payload = HubSpotMapper.from_contact_update(contact)
        res = await self.client.patch(endpoint, json=payload)
        return HubSpotMapper.to_contact(res)

    async def delete_contact(self, contact_id: str) -> bool:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        # Standard HubSpot DELETE returns 204 No Content
        await self.client.delete(endpoint)
        return True

    # --- COMPANIES ---

    async def get_companies(self, limit: int = 100, after: Optional[str] = None) -> List[Company]:
        params = {"limit": limit}
        if after:
            params["after"] = after
        res = await self.client.get(endpoints.COMPANIES, params=params)
        return HubSpotMapper.to_companies_list(res)

    async def get_company(self, company_id: str) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        res = await self.client.get(endpoint)
        return HubSpotMapper.to_company(res)

    async def create_company(self, company: CompanyCreate) -> Company:
        payload = HubSpotMapper.from_company_create(company)
        res = await self.client.post(endpoints.COMPANIES, json=payload)
        return HubSpotMapper.to_company(res)

    async def update_company(self, company_id: str, company: CompanyUpdate) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        payload = HubSpotMapper.from_company_update(company)
        res = await self.client.patch(endpoint, json=payload)
        return HubSpotMapper.to_company(res)

    async def delete_company(self, company_id: str) -> bool:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        await self.client.delete(endpoint)
        return True

    # --- DEALS ---

    async def get_deals(self, limit: int = 100, after: Optional[str] = None) -> List[Deal]:
        params = {"limit": limit}
        if after:
            params["after"] = after
        res = await self.client.get(endpoints.DEALS, params=params)
        return HubSpotMapper.to_deals_list(res)

    async def get_deal(self, deal_id: str) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        res = await self.client.get(endpoint)
        return HubSpotMapper.to_deal(res)

    async def create_deal(self, deal: DealCreate) -> Deal:
        payload = HubSpotMapper.from_deal_create(deal)
        res = await self.client.post(endpoints.DEALS, json=payload)
        return HubSpotMapper.to_deal(res)

    async def update_deal(self, deal_id: str, deal: DealUpdate) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        payload = HubSpotMapper.from_deal_update(deal)
        res = await self.client.patch(endpoint, json=payload)
        return HubSpotMapper.to_deal(res)

    async def delete_deal(self, deal_id: str) -> bool:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        await self.client.delete(endpoint)
        return True
