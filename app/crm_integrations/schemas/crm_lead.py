from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CRMLeadCreate(BaseModel):
    provider: str
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    source: str | None = None
    status: str | None = None


class CRMLeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    external_id: str | None
    full_name: str
    email: EmailStr | None
    phone: str | None
    company: str | None
    status: str | None
    source: str | None
    created_at: datetime
    updated_at: datetime
