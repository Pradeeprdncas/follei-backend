from loguru import logger

from app.domains.messaging.providers.provider_base import MessagingProvider, SendResult


class SmsProviderStub(MessagingProvider):
    async def send(self, recipient: str, body: str, subject: str | None = None,
                   html_body: str | None = None, sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        logger.warning(f"SMS stub: would send to {recipient}: {body[:50]}...")
        return SendResult(
            success=False,
            error="SMS provider not yet implemented",
            status="not_configured",
        )

    def is_configured(self) -> bool:
        return False
