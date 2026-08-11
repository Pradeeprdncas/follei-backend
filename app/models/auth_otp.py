"""Short-lived, one-use passwordless authentication challenges."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Uuid

from app.database.base import Base


class AuthOtpChallenge(Base):
    __tablename__ = "auth_otp_challenges"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # HMAC of the normalized address supports rate limits/lookups without
    # retaining addresses for account-enumeration attempts that match no user.
    email_hash = Column(String(64), nullable=False, index=True)
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code_hash = Column(String(64), nullable=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
