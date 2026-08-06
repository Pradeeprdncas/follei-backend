"""
Zoho CRM Response and Request Mapper.
Maps Zoho CRM payload models to and from unified CRM schemas.
"""
from typing import Any, Dict, List, Optional
from models.schemas import Contact, ContactCreate, ContactUpdate, Company, CompanyCreate, CompanyUpdate, Deal, DealCreate, DealUpdate


class ZohoMapper:
    """Utility class to transform Zoho CRM data structures."""

    # --- CONTACTS ---

    @staticmethod
    def to_contact(data: Dict[str, Any]) -> Contact:
        account_val = data.get("Account_Name")
        company_id = None
        if isinstance(account_val, dict):
            company_id = str(account_val.get("id", ""))

        return Contact(
            id=str(data.get("id", "")),
            first_name=data.get("First_Name"),
            last_name=data.get("Last_Name"),
            email=data.get("Email"),
            phone=data.get("Phone"),
            company_id=company_id,
            created_at=data.get("Created_Time"),
            raw_properties=data,
        )

    @staticmethod
    def to_contacts_list(data: Dict[str, Any]) -> List[Contact]:
        records = data.get("data", [])
        return [ZohoMapper.to_contact(item) for item in records]

    @staticmethod
    def from_contact_create(contact: ContactCreate) -> Dict[str, Any]:
        payload = {}
        if contact.first_name is not None:
            payload["First_Name"] = contact.first_name
        if contact.last_name is not None:
            payload["Last_Name"] = contact.last_name
        if contact.email is not None:
            payload["Email"] = contact.email
        if contact.phone is not None:
            payload["Phone"] = contact.phone
            
        payload.update(contact.properties)
        return {"data": [payload]}

    @staticmethod
    def from_contact_update(contact: ContactUpdate) -> Dict[str, Any]:
        payload = {}
        if contact.first_name is not None:
            payload["First_Name"] = contact.first_name
        if contact.last_name is not None:
            payload["Last_Name"] = contact.last_name
        if contact.email is not None:
            payload["Email"] = contact.email
        if contact.phone is not None:
            payload["Phone"] = contact.phone
            
        payload.update(contact.properties)
        return {"data": [payload]}

    # --- COMPANIES ---

    @staticmethod
    def to_company(data: Dict[str, Any]) -> Company:
        return Company(
            id=str(data.get("id", "")),
            name=data.get("Account_Name"),  # Zoho CRM Accounts use Account_Name
            industry=data.get("Industry"),
            website=data.get("Website"),
            created_at=data.get("Created_Time"),
            raw_properties=data,
        )

    @staticmethod
    def to_companies_list(data: Dict[str, Any]) -> List[Company]:
        records = data.get("data", [])
        return [ZohoMapper.to_company(item) for item in records]

    @staticmethod
    def from_company_create(company: CompanyCreate) -> Dict[str, Any]:
        payload = {
            "Account_Name": company.name
        }
        if company.industry is not None:
            payload["Industry"] = company.industry
        if company.website is not None:
            payload["Website"] = company.website
            
        payload.update(company.properties)
        return {"data": [payload]}

    @staticmethod
    def from_company_update(company: CompanyUpdate) -> Dict[str, Any]:
        payload = {}
        if company.name is not None:
            payload["Account_Name"] = company.name
        if company.industry is not None:
            payload["Industry"] = company.industry
        if company.website is not None:
            payload["Website"] = company.website
            
        payload.update(company.properties)
        return {"data": [payload]}

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
            id=str(data.get("id", "")),
            title=data.get("Deal_Name"),  # Zoho CRM Deals use Deal_Name
            amount=amount,
            stage=data.get("Stage"),
            close_date=data.get("Closing_Date"),
            created_at=data.get("Created_Time"),
            raw_properties=data,
        )

    @staticmethod
    def to_deals_list(data: Dict[str, Any]) -> List[Deal]:
        records = data.get("data", [])
        return [ZohoMapper.to_deal(item) for item in records]

    @staticmethod
    def from_deal_create(deal: DealCreate) -> Dict[str, Any]:
        payload = {
            "Deal_Name": deal.title
        }
        if deal.amount is not None:
            payload["Amount"] = deal.amount
        if deal.stage is not None:
            payload["Stage"] = deal.stage
        if deal.close_date is not None:
            payload["Closing_Date"] = deal.close_date
            
        payload.update(deal.properties)
        return {"data": [payload]}

    @staticmethod
    def from_deal_update(deal: DealUpdate) -> Dict[str, Any]:
        payload = {}
        if deal.title is not None:
            payload["Deal_Name"] = deal.title
        if deal.amount is not None:
            payload["Amount"] = deal.amount
        if deal.stage is not None:
            payload["Stage"] = deal.stage
        if deal.close_date is not None:
            payload["Closing_Date"] = deal.close_date
            
        payload.update(deal.properties)
        return {"data": [payload]}
