"""ERP Adapter base definition."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ERPAdapter(ABC):
    """Abstract interface defining required ERP operations across providers."""

    @abstractmethod
    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a customer record in the ERP."""
        pass

    @abstractmethod
    async def update_customer(self, customer_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates a customer record in the ERP."""
        pass

    @abstractmethod
    async def search_customer(self, query: str) -> List[Dict[str, Any]]:
        """Searches for customers matching a query."""
        pass

    @abstractmethod
    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a customer invoice in the ERP."""
        pass

    @abstractmethod
    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Retrieves details of a specific invoice."""
        pass

    @abstractmethod
    async def create_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a purchase order in the ERP."""
        pass

    @abstractmethod
    async def get_inventory(self, item_id: str) -> Dict[str, Any]:
        """Queries stock/inventory levels of an item."""
        pass

    @abstractmethod
    async def update_inventory(self, item_id: str, quantity: float) -> Dict[str, Any]:
        """Updates inventory levels of an item."""
        pass

    @abstractmethod
    async def create_vendor(self, vendor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a vendor record in the ERP."""
        pass

    @abstractmethod
    async def create_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a sales order in the ERP."""
        pass
