"""Communications domain exceptions."""


class CommunicationError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ProviderNotConfigured(CommunicationError):
    def __init__(self, message: str = "Provider not configured"):
        super().__init__(message)


class ProviderSendError(CommunicationError):
    def __init__(self, channel: str, provider_response: dict | None = None):
        super().__init__(
            f"{channel.upper()} provider failed to send",
            {"channel": channel, "provider_response": provider_response},
        )


class AllProvidersFailed(CommunicationError):
    def __init__(self, channel: str, errors: list[str]):
        super().__init__(
            f"All providers failed for {channel}: {'; '.join(errors)}",
            {"channel": channel, "errors": errors},
        )


class OutboxEnqueueError(CommunicationError):
    def __init__(self, reason: str):
        super().__init__(f"Failed to enqueue message: {reason}")


class RetryExhaustedError(CommunicationError):
    def __init__(self, outbox_id: str, retry_count: int):
        super().__init__(
            f"Outbox message {outbox_id} exhausted after {retry_count} retries",
            {"outbox_id": outbox_id, "retry_count": retry_count},
        )


class WebhookValidationError(CommunicationError):
    def __init__(self, reason: str):
        super().__init__(f"Webhook validation failed: {reason}")
