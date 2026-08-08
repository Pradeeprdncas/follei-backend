"""Stable, client-safe errors for external AI providers."""
from __future__ import annotations


class AIProviderError(RuntimeError):
    """Provider failure whose public message never exposes response bodies or secrets."""

    def __init__(self, code: str, message: str, *, status_code: int, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code
        self.retryable = retryable


class ProviderRateLimitError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "provider_rate_limited",
            "The AI provider is temporarily rate limited. Please retry shortly.",
            status_code=429,
            retryable=True,
        )


class ProviderTimeoutError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "provider_timeout",
            "The AI provider timed out. Please retry.",
            status_code=504,
            retryable=True,
        )


class ProviderUnavailableError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "provider_unavailable",
            "The AI provider is temporarily unavailable. Please retry.",
            status_code=503,
            retryable=True,
        )


class ProviderConfigurationError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "provider_not_configured",
            "AI generation is not configured for this environment.",
            status_code=503,
            retryable=False,
        )


def error_for_status(status_code: int) -> AIProviderError:
    """Map provider HTTP status to a stable public contract."""
    if status_code == 429:
        return ProviderRateLimitError()
    if status_code in {408, 504}:
        return ProviderTimeoutError()
    return ProviderUnavailableError()
