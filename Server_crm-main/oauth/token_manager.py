import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import CRMAuthException
from database.repository import CRMConnectionRepository
from oauth.registry import provider_registry
from oauth.crypto import CryptoUtil

logger = logging.getLogger("crm_gateway.oauth.token_manager")


class TokenManager:
    """
    Manager responsible for retrieving valid tokens, checking expiration,
    triggering token refresh flows automatically, and updating the database.
    """
    def __init__(self, crypto_util: CryptoUtil | None = None):
        self.crypto_util = crypto_util or CryptoUtil()

    async def get_valid_access_token(
        self,
        session: AsyncSession,
        user_id: str,
        provider: str,
        expiry_buffer_seconds: int = 300
    ) -> str:
        """
        Retrieves a valid decrypted access token for the given user and provider.
        If the token is expired or expiring within the buffer time, it refreshes it.
        
        :param session: Active async SQLAlchemy database session.
        :param user_id: ID of the user.
        :param provider: CRM provider identifier.
        :param expiry_buffer_seconds: Seconds buffer before true expiration to trigger a refresh.
        :return: Decrypted valid access token.
        :raises CRMAuthException: If credentials cannot be loaded, decrypted, or refreshed.
        """
        provider_name = provider.strip().lower()
        repo = CRMConnectionRepository(session)
        conn = await repo.get_connection(user_id, provider_name)

        if not conn:
            raise CRMAuthException(
                f"No CRM connection record found in database for user '{user_id}' and provider '{provider_name}'."
            )

        # Decrypt tokens
        try:
            access_token = self.crypto_util.decrypt(conn.access_token)
            refresh_token = self.crypto_util.decrypt(conn.refresh_token)
        except ValueError as e:
            logger.error(f"Failed to decrypt stored tokens for user {user_id}: {str(e)}")
            raise CRMAuthException(
                "Stored CRM authentication credentials could not be decrypted. Re-authorization is required."
            ) from e

        # Expiration validation (default: 5 minute threshold)
        is_expired = False
        if conn.expires_at:
            is_expired = conn.expires_at - timedelta(seconds=expiry_buffer_seconds) <= datetime.utcnow()

        if is_expired:
            logger.info(
                f"Access token for user {user_id} and provider {provider_name} is expired or expiring. Refreshing..."
            )
            if not refresh_token:
                raise CRMAuthException(
                    f"Access token for provider '{provider_name}' is expired and no refresh token is stored."
                )

            # Retrieve the provider from registry to run refresh flow
            oauth_provider = provider_registry.get(provider_name)
            try:
                refresh_data = await oauth_provider.refresh_access_token(refresh_token)
            except Exception as e:
                logger.error(f"Automatic token refresh failed for user {user_id}: {str(e)}")
                raise CRMAuthException(
                    f"Failed to automatically refresh access token for '{provider_name}': {str(e)}"
                ) from e

            # Process new tokens
            new_access_token = refresh_data["access_token"]
            # Fallback to old refresh token if provider did not return a new one
            new_refresh_token = refresh_data.get("refresh_token") or refresh_token
            expires_in = refresh_data["expires_in"]
            new_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Encrypt new tokens
            enc_access_token = self.crypto_util.encrypt(new_access_token)
            enc_refresh_token = self.crypto_util.encrypt(new_refresh_token)

            # Update DB connection
            await repo.save_connection(
                user_id=user_id,
                provider=provider_name,
                access_token=enc_access_token,
                refresh_token=enc_refresh_token,
                expires_at=new_expires_at,
                metadata=refresh_data.get("metadata")
            )

            # Commit the session to persist the new credentials immediately
            await session.commit()
            logger.info(f"Successfully refreshed and saved HubSpot credentials for user {user_id}")
            return new_access_token

        return access_token


# Singleton Global Instance
token_manager = TokenManager()
