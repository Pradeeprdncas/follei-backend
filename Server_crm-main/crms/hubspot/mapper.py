"""
HubSpot Response and Request Mapper.
Maps HubSpot-specific payloads to and from unified CRM schemas.
"""
from typing import Any, Dict, List
from models.schemas import Contact, ContactCreate, ContactUpdate, Company, CompanyCreate, CompanyUpdate, Deal, DealCreate, DealUpdate


class HubSpotMapper:
    """Utility class to transform HubSpot data structures."""

    # --- CONTACTS ---

    @staticmethod
    def to_contact(data: Dict[str, Any]) -> Contact:
        properties = data.get("properties", {})
        return Contact(
            id=str(data.get("id", "")),
            first_name=properties.get("firstname"),
            last_name=properties.get("lastname"),
            email=properties.get("email"),
            phone=properties.get("phone"),
            company_id=properties.get("associatedcompanyid"),
            created_at=data.get("createdAt"),
            raw_properties=properties,
        )

    @staticmethod
    def to_contacts_list(data: Dict[str, Any]) -> List[Contact]:
        results = data.get("results", [])
        return [HubSpotMapper.to_contact(item) for item in results]

    @staticmethod
    def from_contact_create(contact: ContactCreate) -> Dict[str, Any]:
        properties = {}
        if contact.first_name is not None:
            properties["firstname"] = contact.first_name
        if contact.last_name is not None:
            properties["lastname"] = contact.last_name
        if contact.email is not None:
            properties["email"] = contact.email
        if contact.phone is not None:
            properties["phone"] = contact.phone
        
        # Merge custom properties
        properties.update(contact.properties)
        return {"properties": properties}

    @staticmethod
    def from_contact_update(contact: ContactUpdate) -> Dict[str, Any]:
        properties = {}
        if contact.first_name is not None:
            properties["firstname"] = contact.first_name
        if contact.last_name is not None:
            properties["lastname"] = contact.last_name
        if contact.email is not None:
            properties["email"] = contact.email
        if contact.phone is not None:
            properties["phone"] = contact.phone
        
        # Merge custom properties
        properties.update(contact.properties)
        return {"properties": properties}

    # --- COMPANIES ---

    @staticmethod
    def to_company(data: Dict[str, Any]) -> Company:
        properties = data.get("properties", {})
        return Company(
            id=str(data.get("id", "")),
            name=properties.get("name"),
            industry=properties.get("industry"),
            website=properties.get("website"),
            created_at=data.get("createdAt"),
            raw_properties=properties,
        )

    @staticmethod
    def to_companies_list(data: Dict[str, Any]) -> List[Company]:
        results = data.get("results", [])
        return [HubSpotMapper.to_company(item) for item in results]

    @staticmethod
    def from_company_create(company: CompanyCreate) -> Dict[str, Any]:
        properties = {
            "name": company.name
        }
        if company.industry is not None:
            properties["industry"] = company.industry
        if company.website is not None:
            properties["website"] = company.website
            
        properties.update(company.properties)
        return {"properties": properties}

    @staticmethod
    def from_company_update(company: CompanyUpdate) -> Dict[str, Any]:
        properties = {}
        if company.name is not None:
            properties["name"] = company.name
        if company.industry is not None:
            properties["industry"] = company.industry
        if company.website is not None:
            properties["website"] = company.website
            
        properties.update(company.properties)
        return {"properties": properties}

    # --- DEALS ---

    @staticmethod
    def to_deal(data: Dict[str, Any]) -> Deal:
        properties = data.get("properties", {})
        amount_raw = properties.get("amount")
        amount = None
        if amount_raw is not None:
            try:
                amount = float(amount_raw)
            except ValueError:
                pass
                
        return Deal(
            id=str(data.get("id", "")),
            title=properties.get("dealname"),
            amount=amount,
            stage=properties.get("dealstage"),
            close_date=properties.get("closedate"),
            created_at=data.get("createdAt"),
            raw_properties=properties,
        )

    @staticmethod
    def to_deals_list(data: Dict[str, Any]) -> List[Deal]:
        results = data.get("results", [])
        return [HubSpotMapper.to_deal(item) for item in results]

    @staticmethod
    def from_deal_create(deal: DealCreate) -> Dict[str, Any]:
        properties = {
            "dealname": deal.title
        }
        if deal.amount is not None:
            properties["amount"] = str(deal.amount)
        if deal.stage is not None:
            properties["dealstage"] = deal.stage
        if deal.close_date is not None:
            properties["closedate"] = deal.close_date
            
        properties.update(deal.properties)
        return {"properties": properties}

    @staticmethod
    def from_deal_update(deal: DealUpdate) -> Dict[str, Any]:
        properties = {}
        if deal.title is not None:
            properties["dealname"] = deal.title
        if deal.amount is not None:
            properties["amount"] = str(deal.amount)
        if deal.stage is not None:
            properties["dealstage"] = deal.stage
        if deal.close_date is not None:
            properties["closedate"] = deal.close_date
            
        properties.update(deal.properties)
        return {"properties": properties}
