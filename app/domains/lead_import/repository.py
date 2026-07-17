"""Database repository for LeadImportJob and LeadImportRow."""

from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from typing import Any

from app.domains.lead_import.models import LeadImportJob, LeadImportRow
from app.domains.lead_import.constants import RowStatus, ImportStatus


class LeadImportRepository:
    """Data access layer for lead import operations."""

    def __init__(self, db: Session):
        self.db = db

    # ── Jobs ───────────────────────────────────────────────────────────────

    def create_job(self, tenant_id: UUID, filename: str, file_type: str, uploaded_by: str | None = None) -> LeadImportJob:
        job = LeadImportJob(
            tenant_id=tenant_id,
            filename=filename,
            file_type=file_type,
            uploaded_by=uploaded_by,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def get_job(self, job_id: UUID) -> LeadImportJob | None:
        return self.db.get(LeadImportJob, job_id)

    def get_job_by_public_id(self, public_id: str) -> LeadImportJob | None:
        return self.db.execute(
            select(LeadImportJob).where(LeadImportJob.public_id == public_id)
        ).scalar_one_or_none()

    def get_jobs_by_tenant(self, tenant_id: UUID, limit: int = 20, offset: int = 0) -> list[LeadImportJob]:
        return list(self.db.execute(
            select(LeadImportJob)
            .where(LeadImportJob.tenant_id == tenant_id)
            .order_by(LeadImportJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all())

    def update_job_status(self, job_id: UUID, status: str, **extra: Any) -> LeadImportJob | None:
        job = self.get_job(job_id)
        if not job:
            return None
        job.status = status
        for k, v in extra.items():
            setattr(job, k, v)
        self.db.flush()
        return job

    def update_job_statistics(self, job_id: UUID) -> LeadImportJob | None:
        job = self.get_job(job_id)
        if not job:
            return None
        total = self.count_rows(job_id)
        new_count = self.count_rows_by_status(job_id, RowStatus.NEW)
        update_count = self.count_rows_by_status(job_id, RowStatus.UPDATE)
        duplicate_count = self.count_rows_by_status(job_id, RowStatus.DUPLICATE)
        conflict_count = self.count_rows_by_status(job_id, RowStatus.CONFLICT)
        invalid = self.count_rows_by_status(job_id, RowStatus.INVALID)
        job.total_rows = total
        job.valid_rows = new_count + update_count
        job.duplicate_rows = duplicate_count + conflict_count
        job.invalid_rows = invalid
        job.statistics = {
            "total": total,
            "new": new_count,
            "update": update_count,
            "duplicate": duplicate_count,
            "conflict": conflict_count,
            "invalid": invalid,
        }
        self.db.flush()
        return job

    # ── Rows ───────────────────────────────────────────────────────────────

    def bulk_create_rows(self, rows: list[dict]) -> list[LeadImportRow]:
        models = [LeadImportRow(**r) for r in rows]
        self.db.add_all(models)
        self.db.flush()
        return models

    def get_rows_by_job(self, job_id: UUID, status: str | None = None, limit: int | None = None) -> list[LeadImportRow]:
        stmt = select(LeadImportRow).where(LeadImportRow.job_id == job_id).order_by(LeadImportRow.row_index)
        if status:
            stmt = stmt.where(LeadImportRow.status == status)
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_row(self, row_id: UUID) -> LeadImportRow | None:
        return self.db.get(LeadImportRow, row_id)

    def update_row(self, row_id: UUID, **kwargs: Any) -> LeadImportRow | None:
        row = self.get_row(row_id)
        if not row:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        self.db.flush()
        return row

    def bulk_update_rows(self, updates: list[tuple[UUID, dict]]) -> None:
        for row_id, kwargs in updates:
            row = self.get_row(row_id)
            if row:
                for k, v in kwargs.items():
                    setattr(row, k, v)
        self.db.flush()

    def find_matching_leads(self, tenant_id: UUID, email: str = "", phone: str = "") -> list[Any]:
        """Find existing Leads that match by email or phone (case-insensitive).

        Returns a list of Lead objects matching any criterion.
        Imports Lead inline to avoid circular imports at module level.
        """
        from app.models.leads.lead import Lead
        from sqlalchemy import cast, String

        filters = []
        if email:
            filters.append(Lead.email.ilike(email.strip()))
        if phone:
            cleaned = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
            if cleaned.isdigit():
                filters.append(cast(Lead.phone, String) == cleaned)

        if not filters:
            return []

        return list(self.db.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .where(or_(*filters))
        ).scalars().all())

    def mark_duplicates(self, job_id: UUID, duplicate_ids: list[UUID], possible_ids: list[UUID]) -> None:
        for row_id in duplicate_ids:
            self.update_row(row_id, status=RowStatus.DUPLICATE, duplicate=True)
        for row_id in possible_ids:
            self.update_row(row_id, status=RowStatus.DUPLICATE, duplicate=True)

    def count_rows(self, job_id: UUID) -> int:
        return self.db.execute(
            select(func.count(LeadImportRow.id)).where(LeadImportRow.job_id == job_id)
        ).scalar() or 0

    def count_rows_by_status(self, job_id: UUID, status: str) -> int:
        return self.db.execute(
            select(func.count(LeadImportRow.id)).where(
                LeadImportRow.job_id == job_id,
                LeadImportRow.status == status,
            )
        ).scalar() or 0

    def get_selected_rows(self, job_id: UUID) -> list[LeadImportRow]:
        return list(self.db.execute(
            select(LeadImportRow)
            .where(LeadImportRow.job_id == job_id, LeadImportRow.selected.is_(True))
            .order_by(LeadImportRow.row_index)
        ).scalars().all())

    def get_detected_columns(self, job_id: UUID) -> list[str]:
        rows = self.get_rows_by_job(job_id, limit=100)
        columns: set[str] = set()
        for row in rows:
            if row.raw_data:
                columns.update(row.raw_data.keys())
        return sorted(columns)
