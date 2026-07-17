"""Schemas for CRM connector tools."""
from typing import Any, Dict, Optional
from pydantic import BaseModel, EmailStr, Field


class CreateLeadInput(BaseModel):
    """Input parameters to create a new lead in the CRM."""

    first_name: str = Field(..., description="Lead first name")
    last_name: str = Field(..., description="Lead last name")
    email: EmailStr = Field(..., description="Lead email address")
    company: Optional[str] = Field(default=None, description="Company name")
    phone: Optional[str] = Field(default=None, description="Lead telephone number")
    custom_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional custom fields")


class UpdateLeadInput(BaseModel):
    """Input parameters to update an existing lead."""

    lead_id: str = Field(..., description="CRM Lead ID")
    lead_data: Dict[str, Any] = Field(..., description="Key-value pairs to update on the lead")


class SearchContactInput(BaseModel):
    """Input parameters to search for contacts."""

    query: str = Field(..., description="Search criteria (e.g., name or email)")


class CreateOpportunityInput(BaseModel):
    """Input parameters to create a CRM Opportunity/Deal."""

    name: str = Field(..., description="Opportunity name")
    stage: str = Field(..., description="Stage name (e.g., 'Prospecting', 'Closed Won')")
    close_date: str = Field(..., description="ISO Close Date (e.g., '2026-12-31')")
    amount: float = Field(..., description="Estimated deal monetary value", ge=0.0)
    custom_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional custom properties")


class UpdateOpportunityInput(BaseModel):
    """Input parameters to update an existing opportunity."""

    opp_id: str = Field(..., description="CRM Opportunity/Deal ID")
    opp_data: Dict[str, Any] = Field(..., description="Key-value pairs to update on the opportunity")


# JSON Schemas
CRM_CREATE_LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string", "format": "email"},
        "company": {"type": "string"},
        "phone": {"type": "string"},
        "custom_properties": {"type": "object"},
    },
    "required": ["first_name", "last_name", "email"],
}

CRM_UPDATE_LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "lead_id": {"type": "string"},
        "lead_data": {"type": "object"},
    },
    "required": ["lead_id", "lead_data"],
}

CRM_SEARCH_CONTACT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
    },
    "required": ["query"],
}

CRM_CREATE_OPPORTUNITY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "stage": {"type": "string"},
        "close_date": {"type": "string"},
        "amount": {"type": "number"},
        "custom_properties": {"type": "object"},
    },
    "required": ["name", "stage", "close_date", "amount"],
}

CRM_UPDATE_OPPORTUNITY_SCHEMA = {
    "type": "object",
    "properties": {
        "opp_id": {"type": "string"},
        "opp_data": {"type": "object"},
    },
    "required": ["opp_id", "opp_data"],
}
