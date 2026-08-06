from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import CRMConnection, OAuthState

class CRMConnectionRepository:
    """
    Repository class handling CRUD operations for CRM connection records.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_connection(self, user_id: str, provider: str) -> Optional[CRMConnection]:
        """Retrieve connection details for a user and CRM provider."""
        stmt = select(CRMConnection).where(
            CRMConnection.user_id == user_id,
            CRMConnection.provider == provider.lower()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_connections(self, user_id: str) -> List[CRMConnection]:
        """Retrieve all CRM connections for a user."""
        stmt = select(CRMConnection).where(CRMConnection.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_connection(
        self,
        user_id: str,
        provider: str,
        access_token: str,  # Encrypted
        refresh_token: Optional[str],  # Encrypted
        expires_at: Optional[datetime],
        scopes: Optional[str] = None,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> CRMConnection:
        """Upsert a connection record."""
        provider = provider.lower()
        conn_id = f"{user_id}:{provider}"
        
        conn = await self.get_connection(user_id, provider)
        if conn:
            conn.access_token = access_token
            if refresh_token is not None:
                conn.refresh_token = refresh_token
            if expires_at is not None:
                conn.expires_at = expires_at
            if scopes is not None:
                conn.scopes = scopes
            if account_id is not None:
                conn.account_id = account_id
            if account_name is not None:
                conn.account_name = account_name
            if metadata is not None:
                conn.crm_metadata = metadata
            conn.updated_at = datetime.utcnow()
        else:
            conn = CRMConnection(
                id=conn_id,
                user_id=user_id,
                provider=provider,
                account_id=account_id,
                account_name=account_name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scopes=scopes,
                crm_metadata=metadata
            )
            self.session.add(conn)
        
        await self.session.flush()
        return conn

    async def delete_connection(self, user_id: str, provider: str) -> bool:
        """Delete connection details for a user and CRM provider."""
        stmt = delete(CRMConnection).where(
            CRMConnection.user_id == user_id,
            CRMConnection.provider == provider.lower()
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class OAuthStateRepository:
    """
    Repository class handling creation and validation of temporary CSRF states.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_state(
        self,
        state: str,
        user_id: str,
        provider: str,
        expires_in_seconds: int = 600
    ) -> OAuthState:
        """Create a new CSRF state code linked to a user and provider."""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        state_record = OAuthState(
            state=state,
            user_id=user_id,
            provider=provider,
            expires_at=expires_at
        )
        self.session.add(state_record)
        await self.session.flush()
        return state_record

    async def validate_state(self, state: str) -> Optional[OAuthState]:
        """
        Validate a CSRF state code.
        Crucially, this deletes the state from the DB immediately to prevent replay attacks.
        Returns the record if found and not expired, otherwise None.
        """
        stmt = select(OAuthState).where(OAuthState.state == state)
        result = await self.session.execute(stmt)
        state_record = result.scalar_one_or_none()

        if not state_record:
            return None

        # Clean up / delete the state record so it cannot be reused
        await self.session.delete(state_record)
        await self.session.flush()

        # Check expiration
        if state_record.expires_at < datetime.utcnow():
            return None

        return state_record
