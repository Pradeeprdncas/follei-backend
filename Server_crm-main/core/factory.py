"""
CRM Adapter Factory.
Instantiates and configures CRM adapters dynamically based on provider names and credentials.
"""
from typing import Any, Dict, Optional
import httpx

from core.adapter import CRMAdapter
from core.auth import BaseAuthStrategy, OAuth2BearerAuth, APIKeyHeaderAuth, APIKeyQueryAuth, BasicAuth
from core.client import GenericClient
from core.exceptions import CRMAdapterNotFoundException
from crms.hubspot.adapter import HubSpotAdapter
from crms.zoho.adapter import ZohoAdapter
from crms.salesforce.adapter import SalesforceAdapter

# Mapping of provider identifier to adapter class
_ADAPTERS = {
    "hubspot": HubSpotAdapter,
    "zoho": ZohoAdapter,
    "salesforce": SalesforceAdapter,
}


def _build_auth_strategy(credentials: Dict[str, Any]) -> BaseAuthStrategy:
    """Builds the concrete authentication strategy from credentials dictionary."""
    auth_type = credentials.get("auth_type", "oauth2").lower()
    
    if auth_type == "oauth2":
        token = credentials.get("token") or credentials.get("api_key")  # fallback
        if not token:
            if credentials.get("user_id") and credentials.get("db_session"):
                token = "placeholder_token"
            else:
                raise ValueError("Authentication token is required for OAuth2 auth strategy.")
        return OAuth2BearerAuth(token=token)
        
    elif auth_type == "api_key_header":
        api_key = credentials.get("api_key")
        header_name = credentials.get("header_name", "X-API-KEY")
        if not api_key:
            raise ValueError("API Key is required for header-based auth strategy.")
        return APIKeyHeaderAuth(api_key=api_key, header_name=header_name)
        
    elif auth_type == "api_key_query":
        api_key = credentials.get("api_key")
        param_name = credentials.get("param_name", "api_key")
        if not api_key:
            raise ValueError("API Key is required for query-based auth strategy.")
        return APIKeyQueryAuth(api_key=api_key, param_name=param_name)
        
    elif auth_type == "basic":
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or password is None:
            raise ValueError("Username and password are required for Basic auth strategy.")
        return BasicAuth(username=username, password=password)
        
    else:
        raise ValueError(f"Unsupported authentication strategy: {auth_type}")


class AdapterFactory:
    """
    Factory to instantiate CRM adapters with injected GenericClient instances.
    """

    @staticmethod
    def create(
        crm: str,
        credentials: Dict[str, Any],
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> CRMAdapter:
        """
        Instantiate the requested CRM adapter.
        
        :param crm: Name of the CRM provider (e.g., 'hubspot', 'zoho', 'salesforce')
        :param credentials: Dict containing baseURL, auth credentials, default headers, and timeouts.
        :param http_client: Optional external httpx.AsyncClient to share for connection reuse.
        :raises CRMAdapterNotFoundException: If the CRM provider is not registered.
        :raises ValueError: If configuration parameters are invalid or missing.
        """
        crm_key = crm.strip().lower()
        if crm_key not in _ADAPTERS:
            raise CRMAdapterNotFoundException(f"Unsupported CRM provider: '{crm}'")

        base_url = credentials.get("baseURL") or credentials.get("base_url")
        if not base_url:
            raise ValueError("baseURL must be specified in the credentials structure.")

        auth_strategy = _build_auth_strategy(credentials)
        default_headers = credentials.get("default_headers")
        timeout = float(credentials.get("timeout", 30.0))

        # Instantiate the GenericClient
        client = GenericClient(
            baseURL=base_url,
            auth_strategy=auth_strategy,
            default_headers=default_headers,
            timeout=timeout,
            client=http_client,
            user_id=credentials.get("user_id"),
            provider=credentials.get("provider"),
            token_manager=credentials.get("token_manager"),
            db_session=credentials.get("db_session"),
        )

        # Retrieve and return instantiated adapter class
        adapter_class = _ADAPTERS[crm_key]
        return adapter_class(client=client)
