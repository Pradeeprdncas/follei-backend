from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domains.lead_import.constants import ImportStatus
from app.domains.lead_import.router import get_job_status
from app.domains.lead_import.service import LeadImportService, ParserFactory
from app.models.crm import CRMSyncRun, TenantCRMConnection
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.models.integrations.oauth_connection import GoogleWorkspaceConnection
from app.routers.crm_sync import _connection_payload
from app.routers.google_workspace import connections as google_connections
from app.services.knowledge.ingestion_retry import IngestionJobFailed
from app.services.onboarding_state import _client_job_error


_HUBSPOT_WORKER_SPEC = importlib.util.spec_from_file_location(
    "follei_hubspot_worker_failure_test",
    Path(__file__).parents[1] / "app/workers/hubspot_sync_worker.py",
)
assert _HUBSPOT_WORKER_SPEC and _HUBSPOT_WORKER_SPEC.loader
hubspot_worker = importlib.util.module_from_spec(_HUBSPOT_WORKER_SPEC)
_HUBSPOT_WORKER_SPEC.loader.exec_module(hubspot_worker)


class _Query:
    def __init__(self, values, model):
        self.values = values
        self.model = model

    def filter(self, *_args):
        return self

    def first(self):
        return self.values[self.model]

    def all(self):
        return list(self.values.get(self.model, []))


class _WorkerDB:
    def __init__(self, values):
        self.values = values
        self.closed = False

    def query(self, model):
        return _Query(self.values, model)

    def commit(self):
        return None

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_hubspot_pre_sync_failure_is_persisted_on_every_internal_control_record(monkeypatch):
    tenant_id = uuid.uuid4()
    connection = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, last_error=None)
    crm_run = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, status="queued", error=None, completed_at=None)
    ingestion_run = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, status="queued", error=None, started_at=None, completed_at=None)
    ingestion_job = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, status="queued", attempt=0, last_error=None)
    source = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, status="queued")
    db = _WorkerDB({
        TenantCRMConnection: connection,
        CRMSyncRun: crm_run,
        IngestionRun: ingestion_run,
        SourceIngestionJob: ingestion_job,
        KnowledgeSource: source,
    })

    class _FailingOAuth:
        async def valid_access_token(self, *_args):
            raise RuntimeError("refresh failed with correlation diagnostic-42")

    monkeypatch.setattr(hubspot_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(hubspot_worker, "HubSpotOAuthService", _FailingOAuth)

    with pytest.raises(IngestionJobFailed):
        await hubspot_worker.process_hubspot_job({
            "tenant_id": str(tenant_id),
            "connection_id": str(connection.id),
            "crm_run_id": str(crm_run.id),
            "ingestion_run_id": str(ingestion_run.id),
            "ingestion_job_id": str(ingestion_job.id),
            "source_id": str(source.id),
            "resources": ["contact"],
            "page_size": 10,
            "max_pages_per_resource": 1,
            "project_now": False,
        })

    assert "diagnostic-42" in ingestion_job.last_error
    assert ingestion_job.last_error == ingestion_run.error == crm_run.error == connection.last_error
    assert ingestion_job.status == ingestion_run.status == crm_run.status == source.status == "retrying"
    assert db.closed is True


def test_google_and_hubspot_client_payloads_hide_internal_provider_errors():
    google_row = SimpleNamespace(
        id=uuid.uuid4(), email_address="owner@example.com", status="active",
        enabled_resources=["gmail"], last_synced_at=None,
        last_error="provider body containing an internal diagnostic",
    )
    google_payload = google_connections(
        db=_WorkerDB({GoogleWorkspaceConnection: [google_row]}),
        tenant_id=str(uuid.uuid4()),
    )
    # The fake query is model-keyed, so call the serializer path with a tiny
    # query implementation that always returns the single test row.
    assert google_payload["data"]["connections"][0]["last_error"] == "Google Workspace sync failed"

    hubspot_payload = _connection_payload(SimpleNamespace(
        id=uuid.uuid4(), provider="hubspot", status="active",
        external_account_id="portal-1", scopes=[], last_synced_at=None,
        last_error="private HubSpot diagnostic",
    ))
    assert hubspot_payload.last_error == "HubSpot sync failed"
    assert _client_job_error("google_drive_sync", "details") == "Google Workspace sync failed"
    assert _client_job_error("hubspot_sync", "details") == "HubSpot sync failed"


class _LeadDB:
    def __init__(self, job):
        self.job = job

    def commit(self):
        return None

    def refresh(self, _job):
        return None

    def rollback(self):
        return None

    def get(self, _model, _job_id):
        return self.job


class _LeadRepo:
    def __init__(self, job):
        self.job = job
        self.db = _LeadDB(job)

    def delete_rows(self, _job_id):
        return None

    def update_job_status(self, _job_id, status, **extra):
        self.job.status = status
        for key, value in extra.items():
            setattr(self.job, key, value)
        return self.job


@pytest.mark.asyncio
async def test_lead_import_worker_mode_persists_real_error_but_status_payload_is_generic(monkeypatch):
    tenant_id = uuid.uuid4()
    job = SimpleNamespace(
        id=uuid.uuid4(), public_id="lij_test", tenant_id=tenant_id,
        filename="leads.csv", file_type="csv", status="queued",
        uploaded_by=None, total_rows=None, valid_rows=None, duplicate_rows=None,
        invalid_rows=None, statistics=None, error_message=None,
        created_at=datetime.utcnow(), completed_at=None,
    )
    repo = _LeadRepo(job)

    class _Parser:
        async def parse(self, _path):
            raise RuntimeError("CSV parser internal diagnostic-99")

    monkeypatch.setattr(ParserFactory, "get_parser", lambda _kind: _Parser())
    with pytest.raises(RuntimeError, match="diagnostic-99"):
        await LeadImportService(repo).process_upload(
            tenant_id=tenant_id, filename="leads.csv", file_type="csv",
            file_path="unused.csv", existing_job=job, raise_on_failure=True,
        )

    assert job.status == ImportStatus.FAILED
    assert "diagnostic-99" in job.error_message
    response = get_job_status(str(job.id), db=repo.db, authenticated_tenant_id=str(tenant_id))
    assert response.error_message == "Lead import processing failed"
    assert "diagnostic-99" not in response.error_message
