import logging
from app.models.integrations.sms import SmsMessage

logger = logging.getLogger(__name__)


class SmsAutoReplyService:
    async def generate_reply(self, tenant_name: str, history: list[SmsMessage]) -> str:
        if not history:
            return f"Thank you for reaching out to {tenant_name}. A representative will contact you shortly."
        last_inbound = next(
            (m for m in reversed(history) if m.direction == "inbound"),
            None,
        )
        if not last_inbound or not last_inbound.body:
            return f"Thank you for your message. We will get back to you soon."
        return f"Thank you for your message. A {tenant_name} representative will respond shortly."
