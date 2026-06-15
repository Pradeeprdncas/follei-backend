"""Chunk model — stores full text of chunks in PostgreSQL."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)  # full chunk text lives here
    page = Column(Integer, default=0)
    section = Column(String(255), nullable=True)
    heading = Column(String(255), nullable=True)
    tags = Column(JSON, default=list)
    permissions = Column(JSON, default=list)
    embedding_hash = Column(String(64), nullable=True, index=True)  # for dedup
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")
