"""SMS provider — implements CommunicationProvider protocol via Twilio."""
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.config.settings import get_settings


class SmsProvider(CommunicationProvider):
    def __init__(self):
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        account_sid = self._settings.TWILIO_ACCOUNT_SID
        auth_token = self._settings.TWILIO_AUTH_TOKEN
        from_phone = self._settings.TWILIO_FROM_PHONE

        if not account_sid or not auth_token or not from_phone:
            return SendResult(success=False, error="Twilio not configured", status="not_configured")

        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=body[:1600],
                from_=from_phone,
                to=recipient,
            )
            return SendResult(
                success=True,
                provider_message_id=message.sid,
                status="sent",
                raw_response={"sid": message.sid, "status": message.status},
            )
        except Exception as e:
            logger.error(f"Twilio SMS send failed to {recipient}: {e}")
            return SendResult(success=False, error=str(e))

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        results = []
        for r in recipients:
            result = await self.send(
                recipient=r.get("recipient", ""), subject=subject, body=body,
            )
            results.append(result)
        return results

    async def validate(self, recipient: str) -> bool:
        cleaned = recipient.replace("+", "").replace(" ", "").replace("-", "")
        return cleaned.isdigit() and len(cleaned) >= 7

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=bool(self._settings.TWILIO_ACCOUNT_SID and self._settings.TWILIO_AUTH_TOKEN),
            message="Twilio configured" if self._settings.TWILIO_ACCOUNT_SID else "TWILIO_ACCOUNT_SID missing",
        )

    def supports_tracking(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return False

    def supports_attachments(self) -> bool:
        return False

    async def estimate_cost(self, recipient: str, body: str) -> int:
        return 0

    def get_provider_name(self) -> str:
        return "twilio"

    def get_channel(self) -> str:
        return "sms"

    def is_configured(self) -> bool:
        return bool(self._settings.TWILIO_ACCOUNT_SID and self._settings.TWILIO_AUTH_TOKEN)
