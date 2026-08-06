"""
Salesforce CRM Adapter.
Implements the CRMAdapter interface, communicating with Salesforce via GenericClient.
"""
from typing import Any, Dict, List, Optional

from core.adapter import CRMAdapter
from crms.salesforce import endpoints
from crms.salesforce.mapper import SalesforceMapper
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


class SalesforceAdapter(CRMAdapter):
    """
    Adapter to bind Salesforce CRM API endpoints to standardized methods.
    """

    # --- CONTACTS ---

    async def get_contacts(self, limit: int = 100, after: Optional[str] = None) -> List[Contact]:
        query = "SELECT Id, FirstName, LastName, Email, Phone, AccountId, CreatedDate FROM Contact"
        clauses = []
        if after:
            # Simple keyset pagination using Record ID
            clauses.append(f"Id > '{after}'")
            
        if clauses:
            query += f" WHERE {' AND '.join(clauses)}"
        query += f" ORDER BY Id LIMIT {limit}"

        res = await self.client.get(endpoints.QUERY, params={"q": query})
        return SalesforceMapper.to_contacts_list(res)

    async def get_contact(self, contact_id: str) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        res = await self.client.get(endpoint)
        return SalesforceMapper.to_contact(res)

    async def search_contacts(self, filters: Dict[str, Any]) -> List[Contact]:
        query = "SELECT Id, FirstName, LastName, Email, Phone, AccountId, CreatedDate FROM Contact"
        clauses = []
        for key, val in filters.items():
            # Basic escaping of quotes to prevent SOQL injection
            escaped_val = str(val).replace("'", "\\'")
            clauses.append(f"{key} = '{escaped_val}'")
            
        if clauses:
            query += f" WHERE {' AND '.join(clauses)}"
        query += " ORDER BY Id"

        res = await self.client.get(endpoints.QUERY, params={"q": query})
        return SalesforceMapper.to_contacts_list(res)

    async def create_contact(self, contact: ContactCreate) -> Contact:
        payload = SalesforceMapper.from_contact_create(contact)
        res = await self.client.post(endpoints.CONTACTS, json=payload)
        # Salesforce creation response: {"id": "003...", "success": true, "errors": []}
        created_id = res["id"]
        return await self.get_contact(created_id)

    async def update_contact(self, contact_id: str, contact: ContactUpdate) -> Contact:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        payload = SalesforceMapper.from_contact_update(contact)
        # Salesforce updates use PATCH and return 204 No Content
        await self.client.patch(endpoint, json=payload)
        return await self.get_contact(contact_id)

    async def delete_contact(self, contact_id: str) -> bool:
        endpoint = endpoints.CONTACT_DETAIL.format(contact_id=contact_id)
        await self.client.delete(endpoint)
        return True

    # --- COMPANIES ---

    async def get_companies(self, limit: int = 100, after: Optional[str] = None) -> List[Company]:
        query = "SELECT Id, Name, Industry, Website, CreatedDate FROM Account"
        clauses = []
        if after:
            clauses.append(f"Id > '{after}'")
            
        if clauses:
            query += f" WHERE {' AND '.join(clauses)}"
        query += f" ORDER BY Id LIMIT {limit}"

        res = await self.client.get(endpoints.QUERY, params={"q": query})
        return SalesforceMapper.to_companies_list(res)

    async def get_company(self, company_id: str) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        res = await self.client.get(endpoint)
        return SalesforceMapper.to_company(res)

    async def create_company(self, company: CompanyCreate) -> Company:
        payload = SalesforceMapper.from_company_create(company)
        res = await self.client.post(endpoints.COMPANIES, json=payload)
        created_id = res["id"]
        return await self.get_company(created_id)

    async def update_company(self, company_id: str, company: CompanyUpdate) -> Company:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        payload = SalesforceMapper.from_company_update(company)
        await self.client.patch(endpoint, json=payload)
        return await self.get_company(company_id)

    async def delete_company(self, company_id: str) -> bool:
        endpoint = endpoints.COMPANY_DETAIL.format(company_id=company_id)
        await self.client.delete(endpoint)
        return True

    # --- DEALS ---

    async def get_deals(self, limit: int = 100, after: Optional[str] = None) -> List[Deal]:
        query = "SELECT Id, Name, Amount, StageName, CloseDate, CreatedDate FROM Opportunity"
        clauses = []
        if after:
            clauses.append(f"Id > '{after}'")
            
        if clauses:
            query += f" WHERE {' AND '.join(clauses)}"
        query += f" ORDER BY Id LIMIT {limit}"

        res = await self.client.get(endpoints.QUERY, params={"q": query})
        return SalesforceMapper.to_deals_list(res)

    async def get_deal(self, deal_id: str) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        res = await self.client.get(endpoint)
        return SalesforceMapper.to_deal(res)

    async def create_deal(self, deal: DealCreate) -> Deal:
        payload = SalesforceMapper.from_deal_create(deal)
        res = await self.client.post(endpoints.DEALS, json=payload)
        created_id = res["id"]
        return await self.get_deal(created_id)

    async def update_deal(self, deal_id: str, deal: DealUpdate) -> Deal:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        payload = SalesforceMapper.from_deal_update(deal)
        await self.client.patch(endpoint, json=payload)
        return await self.get_deal(deal_id)

    async def delete_deal(self, deal_id: str) -> bool:
        endpoint = endpoints.DEAL_DETAIL.format(deal_id=deal_id)
        await self.client.delete(endpoint)
        return True
