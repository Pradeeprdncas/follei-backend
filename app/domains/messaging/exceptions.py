class MessagingError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ProviderNotConfigured(MessagingError):
    def __init__(self, channel: str):
        super().__init__(
            message=f"{channel.upper()} provider is not configured",
            details={"channel": channel},
        )


class MessageValidationError(MessagingError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Validation failed for '{field}': {reason}",
            details={"field": field, "reason": reason},
        )


class MessageNotFoundError(MessagingError):
    def __init__(self, message_id: str):
        super().__init__(
            message=f"Message not found: {message_id}",
            details={"message_id": message_id},
        )


class ProviderSendError(MessagingError):
    def __init__(self, channel: str, provider_response: dict | None = None):
        super().__init__(
            message=f"{channel.upper()} provider failed to send message",
            details={"channel": channel, "provider_response": provider_response},
        )
