"""Document model — stores metadata about uploaded files."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(32), nullable=False)  # pdf, docx, ppt, email
    status = Column(String(32), default="pending")  # pending, processing, indexed, failed
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)  # comma-separated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
