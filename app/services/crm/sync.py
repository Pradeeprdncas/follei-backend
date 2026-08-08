"""Canonical HubSpot -> PostgreSQL -> FerretDB/Qdrant synchronization."""
from __future__ import annotations

from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.crm_integrations.utils.encryption import EncryptionService
from app.models.crm import CRMRecord, CRMSyncRun, TenantCRMConnection
from app.models.leads.lead import Lead
from app.services.crm.hubspot import HubSpotClient, normalize_hubspot_record
from app.services.knowledge.outbox import enqueue_sync_event, process_sync_event


def _encryption() -> EncryptionService:
    settings = get_settings()
    return EncryptionService(settings.CRM_ENCRYPTION_KEY or settings.SECRET_KEY)


def encrypt_crm_token(token: str) -> str:
    return _encryption().encrypt(token)


def decrypt_crm_token(token: str | None) -> str:
    if not token:
        raise ValueError("CRM connection has no active access token")
    return _encryption().decrypt(token)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _upsert_lead_from_contact(db: Session, tenant_id: UUID, normalized: dict) -> Lead | None:
    email = str(normalized.get("email") or "").strip().lower()
    if not email:
        return None
    lead = db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.email == email).first()
    if not lead:
        lead = Lead(tenant_id=tenant_id, email=email, status="new", profile_data={})
        db.add(lead)
    lead.first_name = normalized.get("first_name") or lead.first_name
    lead.last_name = normalized.get("last_name") or lead.last_name
    lead.company = normalized.get("company") or lead.company
    # CRM lifecycle is evidence, not authority to convert a Follei lead. Only a
    # human conversion command may set Follei status=converted/customer.
    profile = dict(lead.profile_data or {})
    profile.update({
        "crm_provider": "hubspot",
        "crm_external_id": normalized["external_id"],
        "crm_lifecycle_stage": normalized.get("lifecycle_stage"),
        "crm_lead_status": normalized.get("lead_status"),
        "crm_phone": normalized.get("phone"),
    })
    lead.profile_data = profile
    db.flush()
    return lead


async def sync_hubspot(
    db: Session,
    *,
    tenant_id: UUID,
    connection: TenantCRMConnection,
    resources: list[str],
    page_size: int = 100,
    max_pages_per_resource: int = 10,
    project_now: bool = True,
    client_factory: Callable[[str], HubSpotClient] = HubSpotClient,
    run: CRMSyncRun | None = None,
) -> CRMSyncRun:
    if connection.tenant_id != tenant_id or connection.provider != "hubspot":
        raise ValueError("HubSpot connection is not owned by this tenant")
    if run is not None and (run.tenant_id != tenant_id or run.connection_id != connection.id):
        raise ValueError("HubSpot sync run is not owned by this tenant connection")
    run = run or CRMSyncRun(tenant_id=tenant_id, connection_id=connection.id, provider="hubspot", requested_resources=list(resources), object_counts={}, event_ids=[])
    if run.id is None:
        db.add(run)
    run.status = "running"
    db.commit()
    db.refresh(run)
    counts: dict[str, int] = {}
    event_ids: list[str] = []
    cursors = dict(connection.sync_cursor or {})
    client = client_factory(decrypt_crm_token(connection.encrypted_access_token))
    try:
        for object_type in resources:
            after = None
            count = 0
            for _ in range(max_pages_per_resource):
                page = await client.list_page(object_type, limit=page_size, after=after)
                for raw in page.records:
                    normalized = normalize_hubspot_record(object_type, raw)
                    record = db.query(CRMRecord).filter_by(tenant_id=tenant_id, provider="hubspot", object_type=object_type, external_id=normalized["external_id"]).first()
                    unchanged = bool(record and dict(record.canonical_data or {}) == normalized)
                    if record and not unchanged:
                        record.source_revision = int(record.source_revision or 0) + 1
                    elif not record:
                        record = CRMRecord(tenant_id=tenant_id, connection_id=connection.id, provider="hubspot", object_type=object_type, external_id=normalized["external_id"])
                        db.add(record)
                    record.canonical_data = normalized
                    record.provider_updated_at = _parse_datetime(normalized.get("updated_at"))
                    record.synced_at = datetime.utcnow()
                    if object_type == "contact":
                        lead = _upsert_lead_from_contact(db, tenant_id, normalized)
                        record.lead_id = lead.id if lead else None
                    db.flush()
                    if unchanged:
                        count += 1
                        continue
                    event = enqueue_sync_event(
                        db,
                        tenant_id=tenant_id,
                        event_type="crm.record.synced",
                        aggregate_type="crm_record",
                        aggregate_id=record.id,
                        payload={"provider": "hubspot", "object_type": object_type, "external_id": record.external_id, "source_revision": record.source_revision, "normalized": normalized, "raw": raw, "lead_id": str(record.lead_id) if record.lead_id else None, "customer_id": str(record.customer_id) if record.customer_id else None},
                        idempotency_key=f"crm:hubspot:{object_type}:{record.external_id}:r{record.source_revision}",
                    )
                    event_ids.append(str(event.id))
                    count += 1
                after = page.after
                if not after:
                    break
            cursors[object_type] = after
            counts[object_type] = count
        connection.sync_cursor = cursors
        connection.last_synced_at = datetime.utcnow()
        connection.last_error = None
        run.object_counts = counts
        run.event_ids = event_ids
        run.status = "projecting" if event_ids else "completed"
        run.completed_at = datetime.utcnow()
        db.commit()
        if project_now:
            failures = 0
            for event_id in event_ids:
                event = await process_sync_event(event_id)
                if not event or event.status != "completed":
                    failures += 1
            run = db.get(CRMSyncRun, run.id)
            run.status = "completed" if not failures else "projection_retrying"
            if failures:
                run.error = f"{failures} cross-store projection event(s) require retry"
            db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        connection = db.get(TenantCRMConnection, connection.id)
        run = db.get(CRMSyncRun, run.id)
        if connection:
            connection.last_error = str(exc)[:4000]
        if run:
            run.status = "failed"
            run.error = str(exc)[:4000]
            run.completed_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        await client.close()
