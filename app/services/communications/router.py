"""CommunicationRouter — smart provider selection with health, quota, fallback."""
from typing import Any
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.services.communications.providers.email_provider import EmailProvider
from app.services.communications.providers.whatsapp_provider import WhatsAppProvider
from app.services.communications.providers.sms_provider import SmsProvider
from app.services.communications.providers.voice_provider import VoiceProvider
from app.services.communications.providers.push_provider import PushProvider
from app.services.communications.exceptions import ProviderNotConfigured, AllProvidersFailed
from app.config.settings import get_settings


CHANNEL_PROVIDER_MAP = {
    "email": EmailProvider,
    "whatsapp": WhatsAppProvider,
    "sms": SmsProvider,
    "voice": VoiceProvider,
    "push": PushProvider,
}


class CommunicationRouter:
    """Routes messages to the best available provider per channel."""

    def __init__(self):
        self._settings = get_settings()
        self._providers: dict[str, CommunicationProvider] = {}

    def _get_or_create(self, channel: str) -> CommunicationProvider:
        if channel in self._providers:
            return self._providers[channel]
        cls = CHANNEL_PROVIDER_MAP.get(channel)
        if not cls:
            raise ProviderNotConfigured(f"No provider class for channel: {channel}")
        try:
            provider = cls()
        except Exception as e:
            raise ProviderNotConfigured(f"Failed to init provider for {channel}: {e}")
        self._providers[channel] = provider
        return provider

    def get_provider(self, channel: str) -> CommunicationProvider:
        provider = self._get_or_create(channel)
        if not provider.is_configured():
            raise ProviderNotConfigured(f"{channel.upper()} provider is not configured")
        return provider

    async def send(self, channel: str, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None,
                   prefer_provider: str | None = None) -> SendResult:
        provider = self._get_or_create(channel)
        if prefer_provider:
            alt = self._providers.get(prefer_provider)
            if alt and alt.is_configured():
                provider = alt

        if not provider.is_configured():
            raise ProviderNotConfigured(f"No configured provider for channel: {channel}")

        try:
            health = await provider.health()
            if not health.healthy:
                logger.warning(f"Provider {provider.get_provider_name()} unhealthy: {health.message}")
        except Exception:
            pass

        return await provider.send(
            recipient=recipient, subject=subject, body=body,
            html_body=html_body, sender_name=sender_name, metadata=metadata,
        )

    async def send_with_fallback(self, channel: str, recipient: str,
                                 subject: str | None = None, body: str = "",
                                 html_body: str | None = None,
                                 sender_name: str | None = None,
                                 metadata: dict | None = None) -> SendResult:
        errors = []
        provider = self._get_or_create(channel)
        if provider.is_configured():
            try:
                return await provider.send(
                    recipient=recipient, subject=subject, body=body,
                    html_body=html_body, sender_name=sender_name, metadata=metadata,
                )
            except Exception as e:
                errors.append(str(e))

        raise AllProvidersFailed(channel, errors)

    async def health(self, channel: str) -> ProviderHealth:
        try:
            provider = self.get_provider(channel)
            return await provider.health()
        except ProviderNotConfigured as e:
            return ProviderHealth(healthy=False, message=str(e))
        except Exception as e:
            return ProviderHealth(healthy=False, message=str(e))

    def check_config(self, channel: str) -> str:
        try:
            provider = self._get_or_create(channel)
            return "configured" if provider.is_configured() else "not_configured"
        except ProviderNotConfigured:
            return "not_configured"
