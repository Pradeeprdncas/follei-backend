"""Webhook security — signature validation, replay protection, rate limiting."""
import hmac
import hashlib
import time
from typing import Any
from loguru import logger

from app.services.communications.exceptions import WebhookValidationError
from app.config.settings import get_settings


class WebhookValidator:
    """Validates incoming webhook payloads with HMAC signatures."""

    def __init__(self):
        self._settings = get_settings()

    def validate_brevo(self, payload: dict, signature: str | None,
                       timestamp: str | None = None) -> bool:
        if not signature:
            logger.warning("Brevo webhook missing signature")
            return False
        secret = self._settings.BREVO_API_KEY
        if not secret:
            logger.warning("BREVO_API_KEY not set — cannot validate webhook")
            return False
        expected = hmac.new(
            secret.encode(), str(payload).encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def validate_whatsapp(self, mode: str, token: str, challenge: str) -> str | None:
        verify_token = self._settings.WHATSAPP_VERIFY_TOKEN
        if mode == "subscribe" and token == verify_token:
            return challenge
        logger.warning(f"WhatsApp webhook verify failed: mode={mode}")
        return None

    def validate_twilio(self, url: str, params: dict, signature: str) -> bool:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(self._settings.TWILIO_AUTH_TOKEN)
        return validator.validate(url, params, signature)


class ReplayProtection:
    """Prevents replay attacks using nonce or timestamp checking."""

    _seen_nonces: set[str] = set()

    def check_timestamp(self, timestamp_str: str | None, max_age_seconds: int = 300) -> bool:
        if not timestamp_str:
            return False
        try:
            ts = int(timestamp_str)
        except (ValueError, TypeError):
            return False
        now = int(time.time())
        return abs(now - ts) <= max_age_seconds

    def check_nonce(self, nonce: str | None) -> bool:
        if not nonce:
            return False
        if nonce in self._seen_nonces:
            return False
        self._seen_nonces.add(nonce)
        if len(self._seen_nonces) > 100000:
            self._seen_nonces.clear()
        return True
