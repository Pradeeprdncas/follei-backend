import logging
import httpx
from typing import Any, Dict
from urllib.parse import urlencode

from config import settings
from oauth.base import OAuthProvider
from core.exceptions import CRMAuthException, CRMConnectionException, CRMClientException

logger = logging.getLogger("crm_gateway.oauth.hubspot")


class HubSpotOAuthProvider(OAuthProvider):
    """
    OAuth 2.0 Provider implementation for HubSpot.
    Conforms to HubSpot's v3 OAuth APIs.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        scopes: str | None = None,
    ):
        self.client_id = client_id or settings.HUBSPOT_CLIENT_ID
        self.client_secret = client_secret or settings.HUBSPOT_CLIENT_SECRET
        self.redirect_uri = redirect_uri or settings.HUBSPOT_REDIRECT_URI
        self.scopes = scopes or settings.HUBSPOT_SCOPES

    def get_authorization_url(self, state: str) -> str:
        """Generate authorization URL for HubSpot."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
        }
        return f"https://app.hubspot.com/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        url = "https://api.hubapi.com/oauth/v3/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Initiating HubSpot token exchange")
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(url, data=data, headers=headers)
            except httpx.RequestError as e:
                raise CRMConnectionException(f"HubSpot connection failed during code exchange: {str(e)}", original_exception=e)

            if res.status_code != 200:
                self._handle_oauth_error(res)

            token_data = res.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            returned_scopes = token_data.get("scope") or self.scopes

            # Fetch portal metadata using access token
            account_id, account_name = await self._fetch_account_info(access_token)

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "account_id": account_id,
                "account_name": account_name,
                "scopes": returned_scopes,
                "metadata": {
                    "token_type": token_data.get("token_type"),
                    "scopes_list": returned_scopes.split(" ") if isinstance(returned_scopes, str) else returned_scopes
                }
            }

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh HubSpot access token using refresh token."""
        url = "https://api.hubapi.com/oauth/v3/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Initiating HubSpot token refresh")
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(url, data=data, headers=headers)
            except httpx.RequestError as e:
                raise CRMConnectionException(f"HubSpot connection failed during token refresh: {str(e)}", original_exception=e)

            if res.status_code != 200:
                self._handle_oauth_error(res)

            token_data = res.json()
            return {
                "access_token": token_data.get("access_token"),
                # HubSpot may or may not return a new refresh token. Fallback to old one if missing.
                "refresh_token": token_data.get("refresh_token") or refresh_token,
                "expires_in": token_data.get("expires_in"),
                "metadata": {
                    "token_type": token_data.get("token_type")
                }
            }

    async def revoke_token(self, token: str) -> bool:
        """Revoke a token on HubSpot."""
        url = "https://api.hubapi.com/oauth/v1/token/revoke"
        data = {
            "token": token
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Revoking HubSpot token")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, data=data, headers=headers)
                return res.status_code == 204 or res.status_code == 200
            except Exception as e:
                logger.warning(f"Failed to revoke token in HubSpot: {str(e)}")
                return False

    async def _fetch_account_info(self, access_token: str) -> tuple[str, str]:
        """
        Fetch account portal metadata securely.
        Tries Account Info details endpoint first, with fallback to Token Introspection.
        """
        account_id = None
        account_name = None

        # 1. Try Account Info Details API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://api.hubapi.com/account-info/v3/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if res.status_code == 200:
                    data = res.json()
                    account_id = str(data.get("portalId"))
                    account_name = data.get("uiDomain") or f"HubSpot Portal {account_id}"
                    logger.info(f"Successfully retrieved account info via Details API. Portal: {account_id}")
        except Exception as e:
            logger.debug(f"Account Info Details API call failed: {str(e)}")

        # 2. Fallback to Introspection API
        if not account_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(
                        "https://api.hubapi.com/oauth/v3/token/introspect",
                        data={
                            "token": access_token,
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("active") or data.get("hub_id"):
                            account_id = str(data.get("hub_id"))
                            account_name = f"HubSpot Portal {account_id}"
                            logger.info(f"Successfully retrieved account info via Introspection. Portal: {account_id}")
            except Exception as e:
                logger.debug(f"Introspection API call failed: {str(e)}")

        # 3. Default fallback if all calls failed
        if not account_id:
            logger.warning("Could not fetch portal metadata. Using defaults.")
            account_id = "unknown_portal"
            account_name = "HubSpot Account"

        return account_id, account_name

    def _handle_oauth_error(self, response: httpx.Response):
        """Parse OAuth error response and raise unified exception."""
        status_code = response.status_code
        body = response.text
        try:
            error_json = response.json()
            error_code = error_json.get("error") or "oauth_error"
            error_desc = error_json.get("error_description") or error_json.get("message") or body
        except Exception:
            error_code = "oauth_error"
            error_desc = body

        msg = f"HubSpot OAuth error ({status_code}) - {error_code}: {error_desc}"
        logger.error(msg)

        if error_code in ("invalid_grant", "invalid_request", "unauthorized_client", "expired_token"):
            raise CRMAuthException(msg, status_code=status_code, response_body=body)
        
        raise CRMClientException(msg, status_code=status_code, response_body=body)
