from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


CRMObjectType = Literal["contact", "company", "deal"]


class HubSpotConnectionCreate(BaseModel):
    access_token: SecretStr = Field(min_length=10)
    validate_connection: bool = True


class HubSpotSyncRequest(BaseModel):
    resources: list[CRMObjectType] = Field(default_factory=lambda: ["contact", "company", "deal"])
    page_size: int = Field(default=100, ge=1, le=100)
    max_pages_per_resource: int = Field(default=10, ge=1, le=100)
    project_now: bool = False

    @field_validator("resources")
    @classmethod
    def unique_resources(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one CRM resource is required")
        return list(dict.fromkeys(value))


class CRMConnectionResponse(BaseModel):
    id: str
    provider: str
    status: str
    external_account_id: str | None
    scopes: list[str]
    last_synced_at: str | None
    last_error: str | None


class CRMRecordResponse(BaseModel):
    id: str
    provider: str
    object_type: str
    external_id: str
    lead_id: str | None
    customer_id: str | None
    canonical_data: dict[str, Any]
    source_revision: int
    synced_at: str
