"""Email provider — implements CommunicationProvider protocol via Brevo."""
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.services.communications.email_provider import EmailProvider as _EmailProvider
from app.config.settings import get_settings


class EmailProvider(CommunicationProvider):
    def __init__(self):
        self._inner = _EmailProvider()
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        result = await self._inner.send_email(
            to_email=recipient,
            to_name=(metadata or {}).get("to_name", recipient.split("@")[0]),
            subject=subject or "",
            body=body,
            html_body=html_body or body,
        )
        if result.get("success"):
            return SendResult(
                success=True,
                provider_message_id=result.get("message_id"),
                status=result.get("status", "sent"),
                raw_response=result,
            )
        return SendResult(
            success=False,
            error=result.get("error", "Unknown email error"),
            raw_response=result,
        )

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        formatted = []
        for r in recipients:
            formatted.append({
                "email": r.get("recipient"),
                "name": r.get("name", r.get("recipient", "").split("@")[0]),
                **(r.get("metadata", {})),
            })
        result = await self._inner.send_bulk_email(
            recipients=formatted,
            subject=subject or "",
            body=body,
            html_body=html_body or body,
        )
        if result.get("success"):
            return [
                SendResult(success=True, provider_message_id=sub.get("message_id"))
                for sub in result.get("results", [])
            ]
        return [SendResult(success=False, error=result.get("error"))]

    async def validate(self, recipient: str) -> bool:
        import re
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", recipient))

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=bool(self._settings.BREVO_API_KEY),
            message="Brevo configured" if self._settings.BREVO_API_KEY else "BREVO_API_KEY missing",
        )

    def supports_tracking(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return False

    def supports_attachments(self) -> bool:
        return True

    async def estimate_cost(self, recipient: str, body: str) -> int:
        return 0

    def get_provider_name(self) -> str:
        return "brevo"

    def get_channel(self) -> str:
        return "email"

    def is_configured(self) -> bool:
        return bool(self._settings.BREVO_API_KEY)
