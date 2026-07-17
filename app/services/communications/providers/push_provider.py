"""Push notification provider — stub for future Firebase/APNs integration."""
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.config.settings import get_settings


class PushProvider(CommunicationProvider):
    def __init__(self):
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        device_token = metadata.get("device_token") if metadata else None
        logger.warning(f"Push provider stub: would push to {recipient} (token={device_token}): {body[:50]}...")
        return SendResult(
            success=False, error="Push notification provider not yet implemented",
            status="not_implemented",
        )

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        return [await self.send(r.get("recipient", ""), subject, body, metadata=r.get("metadata")) for r in recipients]

    async def validate(self, recipient: str) -> bool:
        return bool(recipient)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(healthy=False, message="Push notifications not yet implemented")

    def supports_tracking(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return False

    def supports_attachments(self) -> bool:
        return True

    async def estimate_cost(self, recipient: str, body: str) -> int:
        return 0

    def get_provider_name(self) -> str:
        return "push_stub"

    def get_channel(self) -> str:
        return "push"

    def is_configured(self) -> bool:
        return False
