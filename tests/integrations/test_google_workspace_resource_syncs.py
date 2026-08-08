from __future__ import annotations

import uuid
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models.integrations.oauth_connection import GoogleWorkspaceConnection
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.services.integrations import google_workspace as google_service
from app.services.knowledge.ingestion_retry import IngestionJobFailed, publish_ingestion_retry


_WORKER_SPEC = importlib.util.spec_from_file_location(
    "follei_google_workspace_worker_under_test",
    Path(__file__).parents[2] / "app/workers/google_workspace_worker.py",
)
assert _WORKER_SPEC and _WORKER_SPEC.loader
worker = importlib.util.module_from_spec(_WORKER_SPEC)
_WORKER_SPEC.loader.exec_module(worker)


class _Producer:
    def __init__(self):
        self.messages: list[tuple[str, dict]] = []

    def send(self, topic, **kwargs):
        self.messages.append((topic, kwargs))

    def flush(self):
        return None


class _Query:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self.model is SourceIngestionJob:
            self.db.source_first_calls += 1
            return self.db.job if self.db.source_first_calls == 1 else None
        if self.model is IngestionRun:
            return self.db.run
        if self.model is GoogleWorkspaceConnection:
            return self.db.connection
        raise AssertionError(f"Unexpected query model: {self.model}")

    def all(self):
        if self.model is SourceIngestionJob:
            return [self.db.job, *self.db.sibling_jobs]
        raise AssertionError(f"Unexpected all() model: {self.model}")


class _DB:
    def __init__(self, job, run, connection, sibling_jobs=()):
        self.job = job
        self.run = run
        self.connection = connection
        self.sibling_jobs = list(sibling_jobs)
        self.source_first_calls = 0
        self.added = []
        self.closed = False

    def query(self, model):
        return _Query(self, model)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None

    def close(self):
        self.closed = True


def _worker_state(resource: str):
    tenant_id, job_id, run_id, connection_id, source_id = (uuid.uuid4() for _ in range(5))
    job = SimpleNamespace(
        id=job_id,
        tenant_id=tenant_id,
        run_id=run_id,
        status="queued",
        attempt=0,
        payload={"resource": resource},
        last_error=None,
    )
    sibling = SimpleNamespace(id=uuid.uuid4(), run_id=run_id, status="completed")
    run = SimpleNamespace(id=run_id, tenant_id=tenant_id, status="queued", document_count=0, error=None)
    connection = SimpleNamespace(
        id=connection_id,
        tenant_id=tenant_id,
        provider_account_id="google-subject",
        sync_cursors={"already_completed": "cursor-existing"},
        last_synced_at=None,
        last_error=None,
    )
    data = {
        "job_id": str(job_id),
        "run_id": str(run_id),
        "source_id": str(source_id),
        "connection_id": str(connection_id),
        "tenant_id": str(tenant_id),
        "resource": resource,
    }
    return data, job, sibling, run, connection


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["gmail", "drive", "calendar", "contacts"])
async def test_each_google_workspace_resource_worker_succeeds_independently(monkeypatch, tmp_path, resource):
    data, job, sibling, run, connection = _worker_state(resource)
    db = _DB(job, run, connection, [sibling])
    producer = _Producer()

    class _Service:
        async def valid_access_token(self, _db, _connection):
            return "provider-token"

        async def fetch_resource(self, token, selected_resource, cursor=None):
            assert token == "provider-token"
            assert selected_resource == resource
            assert cursor is None
            return [{"id": f"{resource}-record"}], f"{resource}-cursor"

    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(worker, "GoogleWorkspaceOAuthService", _Service)
    monkeypatch.setattr(worker, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "store_source", lambda *_args, **_kwargs: "object-key")
    monkeypatch.setattr(worker, "get_producer", lambda: producer)

    await worker.process_google_job(data)

    assert job.status == "completed"
    assert job.attempt == 1
    assert job.payload["record_count"] == 1
    assert sibling.status == "completed"
    assert run.status == "processing"
    assert run.document_count == 2
    assert connection.sync_cursors == {
        "already_completed": "cursor-existing",
        resource: f"{resource}-cursor",
    }
    assert connection.last_error is None
    assert producer.messages[0][1]["value"]["source_metadata"]["resource"] == resource
    assert db.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["gmail", "drive", "calendar", "contacts"])
async def test_each_google_workspace_resource_retries_without_mutating_siblings(monkeypatch, resource):
    data, job, sibling, run, connection = _worker_state(resource)
    sibling.status = "queued"
    db = _DB(job, run, connection, [sibling])

    class _FailingService:
        async def valid_access_token(self, _db, _connection):
            return "provider-token"

        async def fetch_resource(self, _token, selected_resource, cursor=None):
            assert selected_resource == resource
            raise RuntimeError(f"{resource} temporarily unavailable")

    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(worker, "GoogleWorkspaceOAuthService", _FailingService)

    with pytest.raises(IngestionJobFailed) as caught:
        await worker.process_google_job(data)

    assert caught.value.failure.retryable is True
    assert job.status == "retrying"
    assert job.attempt == 1
    assert sibling.status == "queued"
    assert run.status == "retrying"
    assert connection.sync_cursors == {"already_completed": "cursor-existing"}
    assert resource in connection.last_error

    retry_producer = _Producer()
    assert publish_ingestion_retry(
        retry_producer,
        "google-sync",
        data,
        caught.value.failure,
    ) is True
    assert retry_producer.messages == [
        ("google-sync", {"key": data["job_id"], "value": data})
    ]
    assert retry_producer.messages[0][1]["value"]["resource"] == resource
    assert db.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource", "expected_id", "expected_cursor"),
    [
        ("gmail", "message-1", "history-11"),
        ("drive", "file-1", "drive-page-11"),
        ("calendar", "event-1", "calendar-sync-11"),
        ("contacts", "person-1", "contacts-sync-11"),
    ],
)
async def test_all_four_google_provider_adapters_fetch_their_own_resource(monkeypatch, resource, expected_id, expected_cursor):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "message-1"}]})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "history-11"})
        if path.endswith("/files"):
            return httpx.Response(200, json={"files": [{"id": "file-1"}]})
        if path.endswith("/changes/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "drive-page-11"})
        if path.endswith("/events"):
            return httpx.Response(200, json={"items": [{"id": "event-1"}], "nextSyncToken": "calendar-sync-11"})
        if path.endswith("/connections"):
            return httpx.Response(200, json={"connections": [{"id": "person-1"}], "nextSyncToken": "contacts-sync-11"})
        raise AssertionError(f"Unexpected Google request: {request.url}")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        google_service.httpx,
        "AsyncClient",
        lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)),
    )

    records, cursor = await google_service.GoogleWorkspaceOAuthService().fetch_resource(
        "provider-token",
        resource,
    )

    assert records == [{"id": expected_id}]
    assert cursor == expected_cursor
