"""MCP capabilities enumeration."""
from enum import Enum


class MCPCapability(str, Enum):
    """Supported integration capability classes for AI tools."""

    EMAIL = "email"
    CALENDAR = "calendar"
    CRM = "crm"
    WHATSAPP = "whatsapp"
    CHAT = "chat"
    STORAGE = "storage"
    COLLABORATION = "collaboration"
