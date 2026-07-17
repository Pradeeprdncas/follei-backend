from loguru import logger

from app.domains.messaging.providers.provider_base import MessagingProvider, SendResult
from app.services.communications.whatsapp_provider import WhatsAppProvider
from app.config.settings import get_settings


class WhatsAppProviderAdapter(MessagingProvider):
    def __init__(self):
        self._provider = WhatsAppProvider()
        self._settings = get_settings()

    async def send(self, recipient: str, body: str, subject: str | None = None,
                   html_body: str | None = None, sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        media_url = (metadata or {}).get("media_url")
        result = await self._provider.send_message(
            to_phone=recipient,
            message=body,
            media_url=media_url,
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
            error=result.get("error", "Unknown WhatsApp error"),
            raw_response=result,
        )

    def is_configured(self) -> bool:
        return bool(self._settings.WHATSAPP_API_TOKEN and self._settings.WHATSAPP_PHONE_NUMBER_ID)
