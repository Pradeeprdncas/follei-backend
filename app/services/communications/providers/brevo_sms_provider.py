"""Brevo SMS provider — implements the CommunicationProvider protocol.

A sibling to the existing Twilio SmsProvider, sending via Brevo's transactional
SMS API (POST https://api.brevo.com/v3/transactionalSMS/sms). Registered on the
"sms" channel behind the SMS_PROVIDER setting, so a tenant can send SMS via
Brevo or Twilio without any other code change; Twilio stays the default.

Uses httpx and the BREVO_API_KEY already present in .env — the same key the
Brevo email path uses — so no new credential is required.
"""
from __future__ import annotations

import httpx
from loguru import logger

from app.services.communications.protocols import SendResult, ProviderHealth
from app.config.settings import get_settings

_BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
# Brevo requires an alphanumeric sender <= 11 chars; fall back to a safe default.
_MAX_SENDER_LEN = 11


class BrevoSmsProvider:
    def __init__(self):
        self._settings = get_settings()

    def _sender(self, sender_name: str | None) -> str:
        raw = (sender_name or self._settings.BREVO_SENDER_NAME or "Follei").strip()
        # Brevo alphanumeric senders must be <= 11 chars and have no spaces.
        return raw.replace(" ", "")[:_MAX_SENDER_LEN] or "Follei"

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        api_key = self._settings.BREVO_API_KEY
        if not api_key:
            return SendResult(success=False, error="Brevo not configured", status="not_configured")

        payload = {
            "sender": self._sender(sender_name),
            "recipient": recipient.replace(" ", ""),
            "content": body[:918],  # Brevo hard cap is ~918 chars (6 SMS segments)
            "type": "transactional",
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.SERVICE_TIMEOUT) as client:
                resp = await client.post(
                    _BREVO_SMS_URL,
                    headers={"api-key": api_key, "accept": "application/json", "content-type": "application/json"},
                    json=payload,
                )
            if resp.status_code >= 400:
                logger.error(f"Brevo SMS send failed to {recipient}: {resp.status_code} {resp.text}")
                return SendResult(success=False, error=f"HTTP {resp.status_code}: {resp.text}", status="failed")
            data = resp.json() if resp.content else {}
            return SendResult(
                success=True,
                provider_message_id=str(data.get("messageId") or ""),
                status="sent",
                raw_response=data,
            )
        except Exception as e:
            logger.error(f"Brevo SMS send failed to {recipient}: {e}")
            return SendResult(success=False, error=str(e))

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        results = []
        for r in recipients:
            results.append(await self.send(recipient=r.get("recipient", ""), body=body, sender_name=sender_name))
        return results

    async def validate(self, recipient: str) -> bool:
        cleaned = recipient.replace("+", "").replace(" ", "").replace("-", "")
        return cleaned.isdigit() and len(cleaned) >= 7

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=bool(self._settings.BREVO_API_KEY),
            message="Brevo SMS configured" if self._settings.BREVO_API_KEY else "BREVO_API_KEY missing",
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
        return "brevo"

    def get_channel(self) -> str:
        return "sms"

    def is_configured(self) -> bool:
        return bool(self._settings.BREVO_API_KEY)
