"""WhatsApp provider — implements CommunicationProvider protocol via Meta API."""
from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.services.communications.whatsapp_provider import WhatsAppProvider as _WhatsAppProvider
from app.config.settings import get_settings


class WhatsAppProvider(CommunicationProvider):
    def __init__(self):
        self._inner = _WhatsAppProvider()
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        recipient = recipient.replace("+", "").replace(" ", "").replace("-", "")
        media_url = (metadata or {}).get("media_url")
        if media_url:
            result = await self._inner.send_media(
                to_phone=recipient, media_url=media_url, caption=body,
            )
        else:
            result = await self._inner.send_message(
                to_phone=recipient, message=body,
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

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        results = []
        for r in recipients:
            result = await self.send(
                recipient=r.get("recipient", ""),
                subject=subject, body=body,
                metadata=r.get("metadata"),
            )
            results.append(result)
        return results

    async def validate(self, recipient: str) -> bool:
        cleaned = recipient.replace("+", "").replace(" ", "").replace("-", "")
        return cleaned.isdigit() and len(cleaned) >= 7

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=bool(self._settings.WHATSAPP_API_TOKEN and self._settings.WHATSAPP_PHONE_NUMBER_ID),
            message="WhatsApp configured" if self._settings.WHATSAPP_API_TOKEN else "WHATSAPP_API_TOKEN missing",
        )

    def supports_tracking(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return True

    def supports_attachments(self) -> bool:
        return True

    async def estimate_cost(self, recipient: str, body: str) -> int:
        return 0

    def get_provider_name(self) -> str:
        return "meta_whatsapp"

    def get_channel(self) -> str:
        return "whatsapp"

    def is_configured(self) -> bool:
        return bool(self._settings.WHATSAPP_API_TOKEN and self._settings.WHATSAPP_PHONE_NUMBER_ID)
