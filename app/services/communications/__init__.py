"""Communications package — unified provider protocol, router, outbox, workers."""
from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.services.communications.router import CommunicationRouter, CHANNEL_PROVIDER_MAP
from app.services.communications.outbox import OutboxService
from app.services.communications.retry import RetryEngine
from app.services.communications.webhooks import WebhookValidator, ReplayProtection
from app.services.communications.providers import (
    EmailProvider, WhatsAppProvider, SmsProvider, VoiceProvider, PushProvider,
)

__all__ = [
    "CommunicationProvider", "SendResult", "ProviderHealth",
    "CommunicationRouter", "CHANNEL_PROVIDER_MAP",
    "OutboxService", "RetryEngine",
    "WebhookValidator", "ReplayProtection",
    "EmailProvider", "WhatsAppProvider", "SmsProvider", "VoiceProvider", "PushProvider",
]
