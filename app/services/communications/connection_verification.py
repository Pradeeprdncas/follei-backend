"""Live provider verification for tenant communication credentials."""
from __future__ import annotations

import imaplib
import smtplib
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.integrations.channel_connection import TenantChannelConnection
from app.models.integrations.email_connection import TenantEmailConnection
from app.services.communications.email_connections import decrypt_secret


class ProviderVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerificationResult:
    metadata: dict[str, Any]


def verify_gmail_app_password(row: TenantEmailConnection) -> VerificationResult:
    password = decrypt_secret(row.encrypted_app_password).replace(" ", "")
    if not password:
        raise ProviderVerificationError("Gmail app password is missing")
    try:
        with imaplib.IMAP4_SSL(row.imap_host or "imap.gmail.com", timeout=15) as client:
            client.login(row.email_address, password)
        with smtplib.SMTP_SSL(row.smtp_host or "smtp.gmail.com", int(row.smtp_port or 465), timeout=15) as client:
            client.login(row.email_address, password)
    except Exception as exc:
        raise ProviderVerificationError(f"Gmail rejected the mailbox credentials: {exc}") from exc
    return VerificationResult({"imap": True, "smtp": True, "email_address": row.email_address})


async def verify_brevo_email(row: TenantEmailConnection) -> VerificationResult:
    api_key = decrypt_secret(row.encrypted_api_key)
    if not api_key:
        raise ProviderVerificationError("Brevo API key is missing")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.brevo.com/v3/senders", headers={"api-key": api_key, "accept": "application/json"})
        response.raise_for_status()
        senders = response.json().get("senders", [])
    except Exception as exc:
        raise ProviderVerificationError(f"Brevo credential verification failed: {exc}") from exc
    sender = next((item for item in senders if str(item.get("email", "")).lower() == row.email_address.lower()), None)
    if not sender or not sender.get("active"):
        raise ProviderVerificationError("Brevo sender address is missing or not verified/active")
    return VerificationResult({"sender_id": sender.get("id"), "email_address": row.email_address})


async def verify_channel(row: TenantChannelConnection) -> VerificationResult:
    if row.provider == "twilio":
        sid = decrypt_secret(row.encrypted_account_sid)
        token = decrypt_secret(row.encrypted_auth_token)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, params={"PhoneNumber": row.identity}, auth=(sid, token))
            response.raise_for_status()
            numbers = response.json().get("incoming_phone_numbers", [])
        except Exception as exc:
            raise ProviderVerificationError(f"Twilio verification failed: {exc}") from exc
        number = next((item for item in numbers if item.get("phone_number") == row.identity), None)
        capability = "sms" if row.channel == "sms" else "voice"
        capabilities = {str(key).lower(): value for key, value in (number or {}).get("capabilities", {}).items()}
        if not number or not bool(capabilities.get(capability)):
            raise ProviderVerificationError(f"Twilio account does not own {row.identity} with {capability} capability")
        return VerificationResult({"phone_number_sid": number.get("sid"), "capability": capability})

    if row.provider == "meta":
        token = decrypt_secret(row.encrypted_auth_token)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"https://graph.facebook.com/v21.0/{row.provider_account_id}",
                    params={"fields": "display_phone_number,verified_name,quality_rating"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderVerificationError(f"Meta WhatsApp verification failed: {exc}") from exc
        display_number = payload.get("display_phone_number")
        if not display_number:
            raise ProviderVerificationError("Meta did not confirm a WhatsApp phone number")
        requested_digits = "".join(character for character in row.identity if character.isdigit())
        confirmed_digits = "".join(character for character in str(display_number) if character.isdigit())
        if not requested_digits or requested_digits != confirmed_digits:
            raise ProviderVerificationError("Meta confirmed a different WhatsApp phone number")
        return VerificationResult({key: payload.get(key) for key in ("id", "display_phone_number", "verified_name", "quality_rating")})

    if row.provider == "brevo":
        api_key = decrypt_secret(row.encrypted_api_key)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get("https://api.brevo.com/v3/account", headers={"api-key": api_key, "accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderVerificationError(f"Brevo verification failed: {exc}") from exc
        return VerificationResult({"account_email": payload.get("email"), "company_name": payload.get("companyName")})

    raise ProviderVerificationError(f"Unsupported provider {row.provider}")
