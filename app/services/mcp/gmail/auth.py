"""Gmail OAuth2 authentication handler."""
import time
from typing import Any, Dict, Optional
import httpx
from loguru import logger
from mcp.base.exceptions import AuthError


class GmailAuth:
    """Manages Google OAuth2 credentials and token refreshing using HTTPX."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: Optional[str] = None,
        expiry_timestamp: float = 0.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.expiry_timestamp = expiry_timestamp

    def is_token_expired(self) -> bool:
        """Returns True if the access token has expired or is missing."""
        # Refresh 60 seconds before actual expiry to prevent race conditions
        return not self.access_token or (time.time() + 60.0 > self.expiry_timestamp)

    async def get_valid_token(self) -> str:
        """Returns a valid access token, refreshing it if expired."""
        if self.is_token_expired():
            await self.refresh()
        return self.access_token or ""

    async def refresh(self) -> None:
        """Asynchronously refreshes the access token using the refresh token."""
        logger.info("Refreshing Gmail OAuth2 access token...")
        url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, data=payload)
                
            if response.status_code != 200:
                raise AuthError(
                    f"Google OAuth refresh failed ({response.status_code}): {response.text}"
                )
                
            data = response.json()
            self.access_token = data["access_token"]
            # Set absolute expiry timestamp
            expires_in = data.get("expires_in", 3600)
            self.expiry_timestamp = time.time() + float(expires_in)
            logger.info("Gmail OAuth2 access token refreshed successfully.")
        except Exception as e:
            if isinstance(e, AuthError):
                raise
            raise AuthError(f"Exception during Gmail token refresh: {str(e)}") from e
            
    def get_auth_headers(self) -> Dict[str, str]:
        """Generates standard bearer authorization headers."""
        return {"Authorization": f"Bearer {self.access_token}"}
