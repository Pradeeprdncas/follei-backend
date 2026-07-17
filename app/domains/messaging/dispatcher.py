from loguru import logger

from app.domains.messaging.constants import Channel, MessageStatus
from app.domains.messaging.exceptions import ProviderNotConfigured, ProviderSendError
from app.domains.messaging.providers import (
    MessagingProvider,
    EmailProviderAdapter,
    WhatsAppProviderAdapter,
    SmsProviderStub,
)
from app.domains.messaging.providers.provider_base import SendResult


class MessageDispatcher:
    _providers: dict[str, MessagingProvider] | None = None

    def _load_providers(self) -> dict[str, MessagingProvider]:
        if self._providers is not None:
            return self._providers
        self._providers = {
            Channel.EMAIL: EmailProviderAdapter(),
            Channel.WHATSAPP: WhatsAppProviderAdapter(),
            Channel.SMS: SmsProviderStub(),
        }
        return self._providers

    def get_provider(self, channel: str) -> MessagingProvider:
        providers = self._load_providers()
        provider = providers.get(channel)
        if not provider:
            raise ProviderNotConfigured(channel)
        if not provider.is_configured():
            raise ProviderNotConfigured(channel)
        return provider

    async def dispatch(self, channel: str, recipient: str, body: str,
                       subject: str | None = None, html_body: str | None = None,
                       sender_name: str | None = None,
                       metadata: dict | None = None) -> SendResult:
        provider = self.get_provider(channel)
        logger.info(f"Dispatching {channel} message to {recipient}")
        return await provider.send(
            recipient=recipient,
            body=body,
            subject=subject,
            html_body=html_body,
            sender_name=sender_name,
            metadata=metadata,
        )

    def check_health(self, channel: str) -> str:
        providers = self._load_providers()
        provider = providers.get(channel)
        if not provider:
            return "not_configured"
        return "configured" if provider.is_configured() else "not_configured"
