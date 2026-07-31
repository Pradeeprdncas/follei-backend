"""Tenant email connection API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class EmailConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["gmail", "brevo"]
    email_address: EmailStr
    sender_name: str = Field(default="Follei", min_length=1, max_length=160)
    api_key: str | None = Field(default=None, min_length=8, max_length=2048)
    app_password: str | None = Field(default=None, min_length=8, max_length=256)
    auto_reply_enabled: bool = True
    allow_inbound_lead_creation: bool = True
    campaign_enabled: bool = True

    @model_validator(mode="after")
    def validate_provider_secret(self):
        if self.provider == "gmail" and not self.app_password:
            raise ValueError("Gmail requires an app password")
        if self.provider == "brevo" and not self.api_key:
            raise ValueError("Brevo requires an API key")
        return self


class EmailConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_address: EmailStr | None = None
    sender_name: str | None = Field(default=None, min_length=1, max_length=160)
    api_key: str | None = Field(default=None, min_length=8, max_length=2048)
    app_password: str | None = Field(default=None, min_length=8, max_length=256)
    enabled: bool | None = None
    auto_reply_enabled: bool | None = None
    allow_inbound_lead_creation: bool | None = None
    campaign_enabled: bool | None = None


class EmailConnectionResponse(BaseModel):
    id: str
    provider: str
    email_address: EmailStr
    sender_name: str | None
    enabled: bool
    verified: bool
    auto_reply_enabled: bool
    allow_inbound_lead_creation: bool
    campaign_enabled: bool
    status: str
    has_api_key: bool
    has_app_password: bool
    auth_type: str
    oauth_connected: bool
    inbound_ready: bool
    last_polled_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class GmailOAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_address: EmailStr | None = None
    sender_name: str = Field(default="Follei", min_length=1, max_length=160)
    auto_reply_enabled: bool = True
    allow_inbound_lead_creation: bool = True
    campaign_enabled: bool = True


class GmailOAuthStartResponse(BaseModel):
    authorization_url: str
    expires_in: int
