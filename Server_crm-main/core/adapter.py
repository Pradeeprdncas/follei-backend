"""
Generic CRM Adapter Interface.
Defines the CRMAdapter abstract class that all provider-specific adapters inherit from.
Injects the GenericClient instance and enforces a uniform API contract.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.client import GenericClient
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


class CRMAdapter(ABC):
    """
    Abstract Base Class for CRM adapters.
    Ensures that all subclasses consume the GenericClient via dependency injection
    and return standardized Pydantic schemas.
    """

    def __init__(self, client: GenericClient):
        """
        Initialize the adapter with a pre-configured Generic HTTP Client.
        
        :param client: Reusable client instance.
        """
        self.client = client

    # --- CONTACTS ---

    @abstractmethod
    async def get_contacts(self, limit: int = 100, after: Optional[str] = None) -> List[Contact]:
        """Fetch list of contacts with cursor pagination support."""
        pass

    @abstractmethod
    async def get_contact(self, contact_id: str) -> Contact:
        """Fetch a single contact by its unique identifier."""
        pass

    @abstractmethod
    async def search_contacts(self, filters: Dict[str, Any]) -> List[Contact]:
        """Search contacts by specific filter properties."""
        pass

    @abstractmethod
    async def create_contact(self, contact: ContactCreate) -> Contact:
        """Create a new contact in the target CRM."""
        pass

    @abstractmethod
    async def update_contact(self, contact_id: str, contact: ContactUpdate) -> Contact:
        """Update an existing contact in the target CRM."""
        pass

    @abstractmethod
    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact from the target CRM. Returns True if successful."""
        pass

    # --- COMPANIES ---

    @abstractmethod
    async def get_companies(self, limit: int = 100, after: Optional[str] = None) -> List[Company]:
        """Fetch list of companies/accounts with cursor pagination support."""
        pass

    @abstractmethod
    async def get_company(self, company_id: str) -> Company:
        """Fetch a single company by its unique identifier."""
        pass

    @abstractmethod
    async def create_company(self, company: CompanyCreate) -> Company:
        """Create a new company in the target CRM."""
        pass

    @abstractmethod
    async def update_company(self, company_id: str, company: CompanyUpdate) -> Company:
        """Update an existing company in the target CRM."""
        pass

    @abstractmethod
    async def delete_company(self, company_id: str) -> bool:
        """Delete a company from the target CRM. Returns True if successful."""
        pass

    # --- DEALS ---

    @abstractmethod
    async def get_deals(self, limit: int = 100, after: Optional[str] = None) -> List[Deal]:
        """Fetch list of deals/opportunities with cursor pagination support."""
        pass

    @abstractmethod
    async def get_deal(self, deal_id: str) -> Deal:
        """Fetch a single deal by its unique identifier."""
        pass

    @abstractmethod
    async def create_deal(self, deal: DealCreate) -> Deal:
        """Create a new deal in the target CRM."""
        pass

    @abstractmethod
    async def update_deal(self, deal_id: str, deal: DealUpdate) -> Deal:
        """Update an existing deal in the target CRM."""
        pass

    @abstractmethod
    async def delete_deal(self, deal_id: str) -> bool:
        """Delete a deal from the target CRM. Returns True if successful."""
        pass
