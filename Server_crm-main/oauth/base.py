from abc import ABC, abstractmethod
from typing import Any, Dict

class OAuthProvider(ABC):
    """
    Abstract Base Class for all CRM OAuth Providers (HubSpot, Zoho, Salesforce, etc.).
    Defines methods required to implement the OAuth 2.0 Authorization Code Flow.
    """

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """
        Generate the URL to direct the user to start the OAuth authentication flow.
        
        :param state: The secure state identifier to prevent CSRF attacks.
        :return: The provider's authorization URL.
        """
        pass

    @abstractmethod
    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Exchange an authorization code for an access token and a refresh token.
        
        :param code: The code received in the redirect callback.
        :return: A dictionary containing:
            - access_token (str)
            - refresh_token (str)
            - expires_in (int)
            - account_id (str)
            - account_name (str)
            - scopes (list[str] or str)
            - metadata (dict)
        """
        pass

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token using the refresh token.
        
        :param refresh_token: The user's refresh token.
        :return: A dictionary containing:
            - access_token (str)
            - refresh_token (str, optional)
            - expires_in (int)
            - metadata (dict, optional)
        """
        pass

    @abstractmethod
    async def revoke_token(self, token: str) -> bool:
        """
        Revoke the specified token.
        
        :param token: The access or refresh token to revoke.
        :return: True if successfully revoked, False otherwise.
        """
        pass
