from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr
from uuid import UUID


class UserBase(BaseModel):
    tenant_id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
