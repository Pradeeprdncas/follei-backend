"""
Salesforce Response and Request Mapper.
Maps Salesforce CRM payload models to and from unified CRM schemas.
"""
from typing import Any, Dict, List, Optional
from models.schemas import Contact, ContactCreate, ContactUpdate, Company, CompanyCreate, CompanyUpdate, Deal, DealCreate, DealUpdate


class SalesforceMapper:
    """Utility class to transform Salesforce CRM data structures."""

    # --- CONTACTS ---

    @staticmethod
    def to_contact(data: Dict[str, Any]) -> Contact:
        return Contact(
            id=str(data.get("Id", "")),
            first_name=data.get("FirstName"),
            last_name=data.get("LastName"),
            email=data.get("Email"),
            phone=data.get("Phone"),
            company_id=data.get("AccountId"),
            created_at=data.get("CreatedDate"),
            raw_properties=data,
        )

    @staticmethod
    def to_contacts_list(data: Dict[str, Any]) -> List[Contact]:
        records = data.get("records", [])
        return [SalesforceMapper.to_contact(item) for item in records]

    @staticmethod
    def from_contact_create(contact: ContactCreate) -> Dict[str, Any]:
        payload = {}
        if contact.first_name is not None:
            payload["FirstName"] = contact.first_name
        if contact.last_name is not None:
            payload["LastName"] = contact.last_name
        if contact.email is not None:
            payload["Email"] = contact.email
        if contact.phone is not None:
            payload["Phone"] = contact.phone
            
        payload.update(contact.properties)
        return payload

    @staticmethod
    def from_contact_update(contact: ContactUpdate) -> Dict[str, Any]:
        payload = {}
        if contact.first_name is not None:
            payload["FirstName"] = contact.first_name
        if contact.last_name is not None:
            payload["LastName"] = contact.last_name
        if contact.email is not None:
            payload["Email"] = contact.email
        if contact.phone is not None:
            payload["Phone"] = contact.phone
            
        payload.update(contact.properties)
        return payload

    # --- COMPANIES ---

    @staticmethod
    def to_company(data: Dict[str, Any]) -> Company:
        return Company(
            id=str(data.get("Id", "")),
            name=data.get("Name"),  # Salesforce Accounts use Name
            industry=data.get("Industry"),
            website=data.get("Website"),
            created_at=data.get("CreatedDate"),
            raw_properties=data,
        )

    @staticmethod
    def to_companies_list(data: Dict[str, Any]) -> List[Company]:
        records = data.get("records", [])
        return [SalesforceMapper.to_company(item) for item in records]

    @staticmethod
    def from_company_create(company: CompanyCreate) -> Dict[str, Any]:
        payload = {
            "Name": company.name
        }
        if company.industry is not None:
            payload["Industry"] = company.industry
        if company.website is not None:
            payload["Website"] = company.website
            
        payload.update(company.properties)
        return payload

    @staticmethod
    def from_company_update(company: CompanyUpdate) -> Dict[str, Any]:
        payload = {}
        if company.name is not None:
            payload["Name"] = company.name
        if company.industry is not None:
            payload["Industry"] = company.industry
        if company.website is not None:
            payload["Website"] = company.website
            
        payload.update(company.properties)
        return payload

    # --- DEALS ---

    @staticmethod
    def to_deal(data: Dict[str, Any]) -> Deal:
        amount_raw = data.get("Amount")
        amount = None
        if amount_raw is not None:
            try:
                amount = float(amount_raw)
            except ValueError:
                pass

        return Deal(
            id=str(data.get("Id", "")),
            title=data.get("Name"),  # Salesforce Opportunities use Name
            amount=amount,
            stage=data.get("StageName"),  # Salesforce Opportunities use StageName
            close_date=data.get("CloseDate"),  # Salesforce Opportunities use CloseDate
            created_at=data.get("CreatedDate"),
            raw_properties=data,
        )

    @staticmethod
    def to_deals_list(data: Dict[str, Any]) -> List[Deal]:
        records = data.get("records", [])
        return [SalesforceMapper.to_deal(item) for item in records]

    @staticmethod
    def from_deal_create(deal: DealCreate) -> Dict[str, Any]:
        payload = {
            "Name": deal.title
        }
        if deal.amount is not None:
            payload["Amount"] = deal.amount
        if deal.stage is not None:
            payload["StageName"] = deal.stage
        if deal.close_date is not None:
            payload["CloseDate"] = deal.close_date
            
        payload.update(deal.properties)
        return payload

    @staticmethod
    def from_deal_update(deal: DealUpdate) -> Dict[str, Any]:
        payload = {}
        if deal.title is not None:
            payload["Name"] = deal.title
        if deal.amount is not None:
            payload["Amount"] = deal.amount
        if deal.stage is not None:
            payload["StageName"] = deal.stage
        if deal.close_date is not None:
            payload["CloseDate"] = deal.close_date
            
        payload.update(deal.properties)
        return payload
