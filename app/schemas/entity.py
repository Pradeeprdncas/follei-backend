from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntityCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    tenant_id: UUID
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    type: Optional[str] = Field(default=None, min_length=1)
    aliases: Optional[list[str]] = None
    attributes: Optional[dict[str, Any]] = None


class EntityListItem(BaseModel):
    id: UUID
    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)


class EntityListResponse(BaseModel):
    items: list[EntityListItem]


class EntityRelationRead(BaseModel):
    to_entity_id: UUID
    relation: str


class EntityRead(EntityListItem):
    attributes: dict[str, Any] = Field(default_factory=dict)
    relations: list[EntityRelationRead] = Field(default_factory=list)
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
