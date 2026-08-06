from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class ConnectionStatus(BaseModel):
    """Schema representing the connection state of a user's CRM integration."""
    provider: str = Field(..., description="Name of the CRM provider")
    user_id: str = Field(..., description="Identifier of the user who owns the connection")
    is_connected: bool = Field(..., description="Whether a valid connection is active")
    account_id: Optional[str] = Field(None, description="CRM Account/Portal ID")
    account_name: Optional[str] = Field(None, description="CRM Account/Portal Name")
    scopes: Optional[List[str]] = Field(None, description="List of authorized scopes")
    expires_at: Optional[datetime] = Field(None, description="UTC timestamp of access token expiration")
    created_at: Optional[datetime] = Field(None, description="Connection creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Connection last updated timestamp")

    class Config:
        from_attributes = True
        populate_by_name = True


class RefreshResponse(BaseModel):
    """Schema representing the result of a manual token refresh operation."""
    provider: str
    user_id: str
    status: str = Field(..., description="Status of the refresh ('success' or 'error')")
    message: str


class DisconnectResponse(BaseModel):
    """Schema representing the result of disconnecting a CRM provider."""
    provider: str
    user_id: str
    status: str = Field(..., description="Status of the disconnect ('disconnected')")
    message: str
