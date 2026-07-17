from datetime import datetime
from typing import Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class CRMSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    provider: str
    sync_type: Literal["manual", "scheduled", "webhook"] = Field(default="manual", validation_alias=AliasChoices("sync_type", "syncType"))
    resources: list[Literal["contacts", "leads", "deals", "accounts"]] = Field(default_factory=lambda: ["contacts", "leads"])


class CRMSyncResult(BaseModel):
    provider: str
    sync_type: str
    status: str
    records_synced: int
    message: str


class SyncLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    sync_type: str
    status: str
    records_synced: int
    message: str | None
    started_at: datetime
    completed_at: datetime | None
