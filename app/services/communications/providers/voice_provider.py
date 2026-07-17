"""Voice provider — stub with hooks for ElevenLabs/Whisper/Plivo/Twilio Voice."""
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.config.settings import get_settings


class VoiceProvider(CommunicationProvider):
    def __init__(self):
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        logger.warning(f"Voice provider stub: would call {recipient} with TTS: {body[:50]}...")
        return SendResult(
            success=False, error="Voice provider not yet implemented",
            status="not_implemented",
        )

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        return [await self.send(r.get("recipient", ""), subject, body) for r in recipients]

    async def validate(self, recipient: str) -> bool:
        cleaned = recipient.replace("+", "").replace(" ", "").replace("-", "")
        return cleaned.isdigit() and len(cleaned) >= 7

    async def health(self) -> ProviderHealth:
        from app.config.settings import get_settings
        s = get_settings()
        plivo_ok = bool(s.TWILIO_ACCOUNT_SID)
        return ProviderHealth(
            healthy=plivo_ok,
            message="Voice stub (Twilio Voice integration planned)",
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
        return "voice_stub"

    def get_channel(self) -> str:
        return "voice"

    def is_configured(self) -> bool:
        return False
