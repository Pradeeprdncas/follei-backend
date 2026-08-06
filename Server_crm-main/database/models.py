from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class CRMConnection(Base):
    """
    Model representing a connection between a user and a CRM provider.
    """
    __tablename__ = "crm_connections"

    id = Column(String, primary_key=True, index=True)  # Typically formatted as {user_id}:{provider}
    user_id = Column(String, index=True, nullable=False)
    provider = Column(String, index=True, nullable=False)
    account_id = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    access_token = Column(String, nullable=False)  # Stored encrypted
    refresh_token = Column(String, nullable=True)  # Stored encrypted
    expires_at = Column(DateTime, nullable=True)   # UTC expiration time
    scopes = Column(Text, nullable=True)           # Comma-separated list of scopes
    
    # Map to "metadata" in the database while avoiding conflict with declarative Base.metadata
    crm_metadata = Column("metadata", JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthState(Base):
    """
    Model for temporarily storing OAuth state values for CSRF verification.
    """
    __tablename__ = "oauth_states"

    state = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Expiration timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
