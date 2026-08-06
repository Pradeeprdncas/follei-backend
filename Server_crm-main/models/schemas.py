"""
Unified Pydantic Models for CRM Objects.
Defines common, CRM-agnostic representations of Contacts, Companies, and Deals.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class CRMBaseModel(BaseModel):
    """Base schema config for validation."""
    class Config:
        populate_by_name = True
        from_attributes = True


# --- CONTACT SCHEMAS ---

class Contact(CRMBaseModel):
    """Standardized representation of a CRM Contact."""
    id: str = Field(..., description="Unique identifier of the contact in the target CRM")
    first_name: Optional[str] = Field(None, description="First name of the contact")
    last_name: Optional[str] = Field(None, description="Last name of the contact")
    email: Optional[str] = Field(None, description="Email address of the contact")
    phone: Optional[str] = Field(None, description="Phone number of the contact")
    company_id: Optional[str] = Field(None, description="Associated company identifier")
    created_at: Optional[str] = Field(None, description="Timestamp of creation in target CRM")
    raw_properties: Dict[str, Any] = Field(default_factory=dict, description="Raw provider-specific attributes")


class ContactCreate(CRMBaseModel):
    """Payload for creating a CRM Contact."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes")


class ContactUpdate(CRMBaseModel):
    """Payload for updating a CRM Contact."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes to update")


# --- COMPANY SCHEMAS ---

class Company(CRMBaseModel):
    """Standardized representation of a CRM Company/Account."""
    id: str = Field(..., description="Unique identifier of the company in the target CRM")
    name: Optional[str] = Field(None, description="Name of the company")
    industry: Optional[str] = Field(None, description="Industry of the company")
    website: Optional[str] = Field(None, description="Website domain or URL")
    created_at: Optional[str] = Field(None, description="Timestamp of creation in target CRM")
    raw_properties: Dict[str, Any] = Field(default_factory=dict, description="Raw provider-specific attributes")


class CompanyCreate(CRMBaseModel):
    """Payload for creating a CRM Company."""
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes")


class CompanyUpdate(CRMBaseModel):
    """Payload for updating a CRM Company."""
    name: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes to update")


# --- DEAL SCHEMAS ---

class Deal(CRMBaseModel):
    """Standardized representation of a CRM Deal/Opportunity."""
    id: str = Field(..., description="Unique identifier of the deal in the target CRM")
    title: Optional[str] = Field(None, description="Title/Name of the deal")
    amount: Optional[float] = Field(None, description="Value or amount of the deal")
    stage: Optional[str] = Field(None, description="Current pipeline stage of the deal")
    close_date: Optional[str] = Field(None, description="Expected close date")
    created_at: Optional[str] = Field(None, description="Timestamp of creation in target CRM")
    raw_properties: Dict[str, Any] = Field(default_factory=dict, description="Raw provider-specific attributes")


class DealCreate(CRMBaseModel):
    """Payload for creating a CRM Deal."""
    title: str
    amount: Optional[float] = None
    stage: Optional[str] = None
    close_date: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes")


class DealUpdate(CRMBaseModel):
    """Payload for updating a CRM Deal."""
    title: Optional[str] = None
    amount: Optional[float] = None
    stage: Optional[str] = None
    close_date: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes to update")
