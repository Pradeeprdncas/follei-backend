"""
Zoho CRM Adapter.
Implements the CRMAdapter interface, communicating with Zoho via GenericClient.
"""
from typing import Any, Dict, List, Optional

from core.adapter import CRMAdapter
from crms.zoho import endpoints
from crms.zoho.mapper import ZohoMapper
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


class ZohoAdapter(CRMAdapter):
    """
    Adapter to bind Zoho CRM API endpoints to standardized methods.
    """

    # --- CONTACTS ---

    async def get_contacts(self, limit: int = 100, after: Optional[str] = None) -> List[Contact]:
        params = {"per_page": limit}
        if after:
            # Zoho uses integer page numbers (1-indexed)
            params["page"] = int(after)
        res = await self.client.get(endpoints.CONTACTS, params=params)
        return ZohoMapper.to_contacts_list(res)

    async def get_contact(self, contact_id: str) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        res = await self.client.get(endpoint)
        # Zoho returns an array of records in the "data" attribute
        return ZohoMapper.to_contact(res["data"][0])

    async def search_contacts(self, filters: Dict[str, Any]) -> List[Contact]:
        # Translate filters to Zoho's DSL format: (Email:equals:john@example.com)
        criteria_list = []
        for key, val in filters.items():
            criteria_list.append(f"({key}:equals:{val})")
        
        criteria = " and ".join(criteria_list) if criteria_list else ""
        params = {}
        if criteria:
            params["criteria"] = criteria

        res = await self.client.get(endpoints.CONTACT_SEARCH, params=params)
        return ZohoMapper.to_contacts_list(res)

    async def create_contact(self, contact: ContactCreate) -> Contact:
        payload = ZohoMapper.from_contact_create(contact)
        res = await self.client.post(endpoints.CONTACTS, json=payload)
        # Extract the created record's ID and fetch the populated record
        created_id = res["data"][0]["details"]["id"]
        return await self.get_contact(created_id)

    async def update_contact(self, contact_id: str, contact: ContactUpdate) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        payload = ZohoMapper.from_contact_update(contact)
        # Zoho uses PUT for updating records
        await self.client.put(endpoint, json=payload)
        return await self.get_contact(contact_id)

    async def delete_contact(self, contact_id: str) -> bool:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        await self.client.delete(endpoint)
        return True

    # --- COMPANIES ---

    async def get_companies(self, limit: int = 100, after: Optional[str] = None) -> List[Company]:
        params = {"per_page": limit}
        if after:
            params["page"] = int(after)
        res = await self.client.get(endpoints.COMPANIES, params=params)
        return ZohoMapper.to_companies_list(res)

    async def get_company(self, company_id: str) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        res = await self.client.get(endpoint)
        return ZohoMapper.to_company(res["data"][0])

    async def create_company(self, company: CompanyCreate) -> Company:
        payload = ZohoMapper.from_company_create(company)
        res = await self.client.post(endpoints.COMPANIES, json=payload)
        created_id = res["data"][0]["details"]["id"]
        return await self.get_company(created_id)

    async def update_company(self, company_id: str, company: CompanyUpdate) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        payload = ZohoMapper.from_company_update(company)
        await self.client.put(endpoint, json=payload)
        return await self.get_company(company_id)

    async def delete_company(self, company_id: str) -> bool:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        await self.client.delete(endpoint)
        return True

    # --- DEALS ---

    async def get_deals(self, limit: int = 100, after: Optional[str] = None) -> List[Deal]:
        params = {"per_page": limit}
        if after:
            params["page"] = int(after)
        res = await self.client.get(endpoints.DEALS, params=params)
        return ZohoMapper.to_deals_list(res)

    async def get_deal(self, deal_id: str) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        res = await self.client.get(endpoint)
        return ZohoMapper.to_deal(res["data"][0])

    async def create_deal(self, deal: DealCreate) -> Deal:
        payload = ZohoMapper.from_deal_create(deal)
        res = await self.client.post(endpoints.DEALS, json=payload)
        created_id = res["data"][0]["details"]["id"]
        return await self.get_deal(created_id)

    async def update_deal(self, deal_id: str, deal: DealUpdate) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        payload = ZohoMapper.from_deal_update(deal)
        await self.client.put(endpoint, json=payload)
        return await self.get_deal(deal_id)

    async def delete_deal(self, deal_id: str) -> bool:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        await self.client.delete(endpoint)
        return True
