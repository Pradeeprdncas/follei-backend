import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Integer, Float, Text, Boolean, Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id
from app.models.tenancy import Tenant


class LeadImportJob(Base):
    """Tracks a lead import upload and its processing pipeline state."""

    __tablename__ = "lead_import_jobs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)

    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # csv, xlsx, xls, pdf, docx, txt, png, jpg, jpeg
    status = Column(String, nullable=False, default="pending", index=True)  # pending → processing → parsing → extracting → validating → preview_ready → committed | failed
    uploaded_by = Column(String, nullable=True)

    total_rows = Column(Integer, nullable=True)
    valid_rows = Column(Integer, nullable=True)
    duplicate_rows = Column(Integer, nullable=True)
    invalid_rows = Column(Integer, nullable=True)

    statistics = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    tenant = relationship(Tenant)
    rows = relationship("LeadImportRow", back_populates="job", cascade="all, delete-orphan", lazy="dynamic")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("LeadImportJob")


class LeadImportRow(Base):
    """Stores each extracted row from a lead import before committing to Lead."""

    __tablename__ = "lead_import_rows"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    job_id = Column(Uuid(as_uuid=True), ForeignKey("lead_import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)

    row_index = Column(Integer, nullable=False)  # 0-based row position in source
    raw_data = Column(JSONB, nullable=False, default=dict)
    normalized_data = Column(JSONB, nullable=True)
    extracted_data = Column(JSONB, nullable=True)  # AI-extracted lead fields (first_name, last_name, email, etc.)
    confidence = Column(Float, nullable=True)

    duplicate = Column(Boolean, default=False, index=True)
    duplicate_of = Column(Uuid(as_uuid=True), nullable=True)  # points to the matched Lead.id
    match_reason = Column(String, nullable=True)  # "email", "phone", "email+phone", "linkedin", "website"
    status = Column(String, nullable=False, default="pending", index=True)  # pending, new, update, duplicate, conflict, invalid, committed, skipped
    selected = Column(Boolean, default=True)
    error = Column(Text, nullable=True)

    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("LeadImportJob", back_populates="rows")
    tenant = relationship(Tenant)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("LeadImportRow")
