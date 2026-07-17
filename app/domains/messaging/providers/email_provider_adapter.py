from loguru import logger

from app.domains.messaging.providers.provider_base import MessagingProvider, SendResult
from app.services.communications.email_provider import EmailProvider
from app.config.settings import get_settings


class EmailProviderAdapter(MessagingProvider):
    def __init__(self):
        self._provider = EmailProvider()
        self._settings = get_settings()

    async def send(self, recipient: str, body: str, subject: str | None = None,
                   html_body: str | None = None, sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        to_name = (metadata or {}).get("to_name", recipient)
        result = await self._provider.send_email(
            to_email=recipient,
            to_name=to_name,
            subject=subject or "",
            body=body,
            html_body=html_body,
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

    def is_configured(self) -> bool:
        return bool(self._settings.BREVO_API_KEY)
