"""CRM integration connector package."""
from mcp.crm.service import CRMService
from mcp.crm.connector import CRMConnector
from mcp.crm.tools import (
    CRMCreateLeadTool,
    CRMUpdateLeadTool,
    CRMSearchContactTool,
    CRMCreateOpportunityTool,
    CRMUpdateOpportunityTool,
)

__all__ = [
    "CRMService",
    "CRMConnector",
    "CRMCreateLeadTool",
    "CRMUpdateLeadTool",
    "CRMSearchContactTool",
    "CRMCreateOpportunityTool",
    "CRMUpdateOpportunityTool",
]
