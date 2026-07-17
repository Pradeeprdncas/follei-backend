"""CRM Adaptor base definition and exports."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class CRMAdapter(ABC):
    """Abstract interface defining required CRM operations across providers."""

    @abstractmethod
    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a lead/contact in the CRM."""
        pass

    @abstractmethod
    async def update_lead(self, lead_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates a lead/contact in the CRM."""
        pass

    @abstractmethod
    async def search_contact(self, query: str) -> List[Dict[str, Any]]:
        """Searches for contacts matching name or email."""
        pass

    @abstractmethod
    async def create_opportunity(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates an opportunity/deal in the CRM."""
        pass

    @abstractmethod
    async def update_opportunity(self, opp_id: str, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an opportunity/deal in the CRM."""
        pass
