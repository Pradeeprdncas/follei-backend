import os
import re
from typing import Any, Callable
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from app.config.settings import get_settings


class SmsProviderError(RuntimeError):
    pass


def normalize_phone(phone: str | None, field_name: str = "phone number") -> str:
    value = (phone or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    digits = re.sub(r"\D", "", value)
    if value.startswith("+") and 8 <= len(digits) <= 15 and not digits.startswith("0"):
        return f"+{digits}"
    settings = get_settings()
    country_digits = re.sub(r"\D", "", settings.SMS_DEFAULT_COUNTRY_CODE)
    if len(digits) == 10 and country_digits:
        return f"+{country_digits}{digits}"
    raise ValueError(f"{field_name} must be in E.164 format")


class TwilioClient:
    def __init__(
        self,
        *,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_phone: str | None = None,
        client_factory: Callable[[str, str], Any] = Client,
    ) -> None:
        settings = get_settings()
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        configured_from = from_phone or settings.TWILIO_FROM_PHONE
        if not self.account_sid:
            raise SmsProviderError("TWILIO_ACCOUNT_SID is not configured")
        if not self.auth_token:
            raise SmsProviderError("TWILIO_AUTH_TOKEN is not configured")
        if not configured_from:
            raise SmsProviderError("TWILIO_FROM_PHONE is not configured")
        try:
            self.from_phone = normalize_phone(configured_from, "TWILIO_FROM_PHONE")
        except ValueError as exc:
            raise SmsProviderError(str(exc)) from exc
        self._client = client_factory(self.account_sid, self.auth_token)

    def send_sms(self, to_phone: str, body: str) -> dict[str, str]:
        try:
            recipient = normalize_phone(to_phone, "recipient phone number")
            sent = self._client.messages.create(body=body, from_=self.from_phone, to=recipient)
        except ValueError as exc:
            raise SmsProviderError(str(exc)) from exc
        except TwilioRestException as exc:
            raise SmsProviderError(f"Twilio delivery failed: {exc.msg or str(exc)}") from exc
        except Exception as exc:
            raise SmsProviderError(f"Twilio delivery failed: {exc}") from exc
        return {"sid": sent.sid, "status": sent.status or "sent", "from": self.from_phone, "to": recipient}
