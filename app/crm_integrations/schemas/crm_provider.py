from typing import Literal
from pydantic import BaseModel, ConfigDict


CRMProviderStatus = Literal["available", "connected", "not_configured"]


class CRMProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    provider: str
    description: str
    category: str
    icon: str
    logo: str
    website: str
    enabled: bool
    oauth: bool
    connected: bool
    status: CRMProviderStatus
    connect_url: str
    login_url_endpoint: str
    supports: list[str]
    features: dict[str, bool]
    default_scopes: list[str] | None = None
    login_url: str | None = None


class CRMProvidersResponse(BaseModel):
    crms: list[CRMProviderResponse]
