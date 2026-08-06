"""
Pluggable Authentication Strategies.
Implements the Strategy pattern to support different authentication mechanisms (OAuth2 Bearer, API Keys in headers, API Keys in query parameters, and Basic Auth).
"""
import base64
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAuthStrategy(ABC):
    """Abstract base class representing an authentication strategy."""

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers required for this authentication strategy.
        Returns a dictionary of headers (e.g., {'Authorization': 'Bearer ...'}).
        """
        return {}

    def get_auth_params(self) -> Dict[str, Any]:
        """
        Get query parameters required for this authentication strategy.
        Returns a dictionary of query parameters.
        """
        return {}


class OAuth2BearerAuth(BaseAuthStrategy):
    """OAuth2 Bearer Token Authentication (e.g., HubSpot OAuth, Zoho OAuth)."""

    def __init__(self, token: str):
        self.token = token

    def get_auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class APIKeyHeaderAuth(BaseAuthStrategy):
    """API Key authentication passed in a custom HTTP header (e.g., X-API-KEY)."""

    def __init__(self, api_key: str, header_name: str = "X-API-KEY"):
        self.api_key = api_key
        self.header_name = header_name

    def get_auth_headers(self) -> Dict[str, str]:
        return {self.header_name: self.api_key}


class APIKeyQueryAuth(BaseAuthStrategy):
    """API Key authentication passed as a query parameter (e.g., ?api_key=...)."""

    def __init__(self, api_key: str, param_name: str = "api_key"):
        self.api_key = api_key
        self.param_name = param_name

    def get_auth_params(self) -> Dict[str, Any]:
        return {self.param_name: self.api_key}


class BasicAuth(BaseAuthStrategy):
    """Standard HTTP Basic Authentication."""

    def __init__(self, username: str, password: str):
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode("ascii")).decode("ascii")
        self.auth_value = f"Basic {encoded}"

    def get_auth_headers(self) -> Dict[str, str]:
        return {"Authorization": self.auth_value}
