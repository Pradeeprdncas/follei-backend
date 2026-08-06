import logging
from typing import Dict
from core.exceptions import CRMAdapterNotFoundException
from oauth.base import OAuthProvider
from oauth.hubspot import HubSpotOAuthProvider

logger = logging.getLogger("crm_gateway.oauth.registry")


class StubOAuthProvider(OAuthProvider):
    """
    Stub provider representing an extension point for non-implemented CRM providers.
    """
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def get_authorization_url(self, state: str) -> str:
        raise NotImplementedError(
            f"OAuth 2.0 flow is not yet implemented for provider '{self.provider_name}'."
        )

    async def exchange_code(self, code: str) -> dict:
        raise NotImplementedError(
            f"OAuth 2.0 flow is not yet implemented for provider '{self.provider_name}'."
        )

    async def refresh_access_token(self, refresh_token: str) -> dict:
        raise NotImplementedError(
            f"OAuth 2.0 flow is not yet implemented for provider '{self.provider_name}'."
        )

    async def revoke_token(self, token: str) -> bool:
        raise NotImplementedError(
            f"OAuth 2.0 flow is not yet implemented for provider '{self.provider_name}'."
        )


class ProviderRegistry:
    """
    Registry that links CRM provider name strings to their corresponding OAuthProvider implementations.
    """
    def __init__(self):
        self._providers: Dict[str, OAuthProvider] = {}

    def register(self, name: str, provider: OAuthProvider) -> None:
        """Register a new OAuth provider."""
        key = name.strip().lower()
        self._providers[key] = provider
        logger.info(f"Registered OAuth provider '{key}'")

    def get(self, name: str) -> OAuthProvider:
        """Retrieve a registered OAuth provider or raise a structured error."""
        key = name.strip().lower()
        provider = self._providers.get(key)
        if not provider:
            raise CRMAdapterNotFoundException(f"Unsupported OAuth provider: '{name}'")
        return provider


# Global Registry Instance
provider_registry = ProviderRegistry()

# Register core providers
provider_registry.register("hubspot", HubSpotOAuthProvider())
provider_registry.register("zoho", StubOAuthProvider("Zoho"))
provider_registry.register("salesforce", StubOAuthProvider("Salesforce"))
