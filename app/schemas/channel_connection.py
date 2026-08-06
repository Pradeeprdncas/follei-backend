"""Public API contracts for non-email communication connections."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["sms", "whatsapp", "voice"]
    provider: Literal["twilio", "meta"]
    identity: str = Field(min_length=3, max_length=255, description="Provider-owned sending phone number or WhatsApp display number")
    provider_account_id: str | None = Field(default=None, max_length=255, description="Meta phone-number ID when provider=meta")
    account_sid: str | None = Field(default=None, min_length=6, max_length=255)
    auth_token: str | None = Field(default=None, min_length=6, max_length=2048)
    api_key: str | None = Field(default=None, min_length=6, max_length=2048)
    inbound_enabled: bool = True
    campaign_enabled: bool = False
    compliance_policy_version: str | None = Field(default=None, max_length=32)
    opt_in_acknowledged: bool = False
    stop_help_acknowledged: bool = False

    @model_validator(mode="after")
    def validate_provider(self):
        allowed = {
            "sms": {"twilio"},
            "voice": {"twilio"},
            "whatsapp": {"meta"},
        }
        if self.provider not in allowed[self.channel]:
            raise ValueError(f"{self.provider} is not supported for {self.channel}")
        if self.provider == "twilio" and (not self.account_sid or not self.auth_token):
            raise ValueError("Twilio requires account_sid and auth_token")
        if self.provider == "meta" and (not self.provider_account_id or not self.auth_token):
            raise ValueError("Meta WhatsApp requires provider_account_id and auth_token")
        if self.campaign_enabled and self.channel in {"sms", "whatsapp"}:
            if not (self.compliance_policy_version and self.opt_in_acknowledged and self.stop_help_acknowledged):
                raise ValueError("Campaign messaging requires policy version plus opt-in and STOP/HELP acknowledgement")
        return self


class ChannelConnectionResponse(BaseModel):
    id: str
    channel: str
    provider: str
    identity: str
    provider_account_id: str | None
    enabled: bool
    verified: bool
    inbound_enabled: bool
    campaign_enabled: bool
    compliance_ready: bool
    status: str
    verified_at: datetime | None
    last_verified_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ChannelComplianceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(min_length=1, max_length=32)
    opt_in_acknowledged: bool
    stop_help_acknowledged: bool
    campaign_enabled: bool = True
