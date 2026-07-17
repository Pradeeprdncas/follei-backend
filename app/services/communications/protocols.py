"""Unified provider protocol — all channels implement this interface."""
from typing import Protocol, runtime_checkable, Any
from dataclasses import dataclass


@dataclass
class SendResult:
    success: bool
    provider_message_id: str | None = None
    status: str = ""
    raw_response: dict | None = None
    error: str | None = None
    cost: int | None = None


@dataclass
class ProviderHealth:
    healthy: bool
    latency_ms: int | None = None
    message: str = ""


@runtime_checkable
class CommunicationProvider(Protocol):
    async def send(self, recipient: str, subject: str | None,
                   body: str, html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult: ...

    async def send_batch(self, recipients: list[dict], subject: str | None,
                         body: str, html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]: ...

    async def validate(self, recipient: str) -> bool: ...

    async def health(self) -> ProviderHealth: ...

    def supports_tracking(self) -> bool: ...

    def supports_templates(self) -> bool: ...

    def supports_attachments(self) -> bool: ...

    async def estimate_cost(self, recipient: str, body: str) -> int: ...

    def get_provider_name(self) -> str: ...

    def get_channel(self) -> str: ...

    def is_configured(self) -> bool: ...
