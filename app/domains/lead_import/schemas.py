"""Pydantic schemas for the Lead Import API layer."""

from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, Field


# ── Request Schemas ────────────────────────────────────────────────────────

class LeadImportUploadResponse(BaseModel):
    """Returned immediately after file upload."""
    job_id: str
    public_id: str
    filename: str
    file_type: str
    status: str
    message: str = "File uploaded successfully. Processing in background."


# ── Response Schemas ───────────────────────────────────────────────────────

class LeadImportJobResponse(BaseModel):
    """Full job status and progress."""
    id: str
    public_id: str
    tenant_id: str
    filename: str
    file_type: str
    status: str
    uploaded_by: str | None = None
    total_rows: int | None = None
    valid_rows: int | None = None
    duplicate_rows: int | None = None
    invalid_rows: int | None = None
    statistics: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class LeadImportRowPreview(BaseModel):
    """A single row in the preview response."""
    id: str
    row_index: int
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None = None
    extracted_data: dict[str, Any] | None = None
    confidence: float | None = None
    confidence_reason: str | None = None
    duplicate_probability: int | None = None
    source_page: int | None = None
    source_row: int | None = None
    quality_score: int | None = None
    quality_grade: str | None = None
    quality_reasons: list[str] | None = None
    quality_flags: list[str] | None = None
    intelligence: dict[str, Any] | None = None
    duplicate: bool = False
    duplicate_of: str | None = None
    match_reason: str | None = None
    status: str
    selected: bool = True
    error: str | None = None


class LeadImportPreviewResponse(BaseModel):
    """Full preview of extracted leads before user confirmation."""
    job_id: str
    public_id: str
    filename: str
    file_type: str
    status: str
    detected_columns: list[str] = Field(default_factory=list)
    statistics: dict[str, Any] | None = None
    total_rows: int = 0
    document_classification: dict[str, Any] | None = None
    new_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    update_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    duplicate_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    conflict_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    invalid_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    spam_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    needs_review_rows: list[LeadImportRowPreview] = Field(default_factory=list)
    ignored_rows: list[LeadImportRowPreview] = Field(default_factory=list)


class LeadImportCommitResponse(BaseModel):
    """Returned after successfully committing an import."""
    job_id: str
    public_id: str
    status: str
    total_imported: int
    total_new: int = 0
    total_updated: int = 0
    total_duplicates: int = 0
    total_conflicts: int = 0
    total_invalid: int = 0
    message: str


# ── Row Edit / Review Schemas ─────────────────────────────────────────────

class RowUpdateRequest(BaseModel):
    """Update a single row's extracted data fields."""
    updates: dict[str, Any]


class BulkActionRequest(BaseModel):
    """Perform a bulk action on selected rows."""
    action: str  # "ignore", "reset", "spam", "select", "deselect"
    row_ids: list[UUID]


class BulkActionResponse(BaseModel):
    """Result of a bulk action."""
    action: str
    affected_rows: int
