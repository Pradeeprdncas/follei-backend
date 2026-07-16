from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import relationship
from app.database.base import Base


class CRMAccount(Base):
    __tablename__ = "crm_accounts"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), index=True, nullable=False)
    account_name = Column(String(255), nullable=False)
    external_account_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    connections = relationship("CRMConnection", back_populates="account")
