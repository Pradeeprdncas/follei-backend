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
        if path.endswith("/messages/message-1"):
            return httpx.Response(200, json={
                "id": "message-1",
                "threadId": "thread-1",
                "payload": {"mimeType": "text/plain", "body": {"data": "SGVsbG8gZnJvbSBHbWFpbA=="}},
            })
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "history-11"})
        if path.endswith("/files"):
            return httpx.Response(200, json={"files": [{"id": "file-1", "mimeType": "text/plain"}]})
        if path.endswith("/files/file-1"):
            return httpx.Response(200, content=b"Drive file content", headers={"content-type": "text/plain"})
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

    assert records[0]["id"] == expected_id
    if resource == "gmail":
        assert records[0]["body_text"] == "Hello from Gmail"
    if resource == "drive":
        assert records[0]["content_text"] == "Drive file content"
        assert records[0]["content_status"] == "synced"
    assert cursor == expected_cursor


@pytest.mark.asyncio
async def test_gmail_sync_fetches_full_body_and_attachment_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "message-1"}]})
        if path.endswith("/messages/message-1"):
            return httpx.Response(200, json={
                "id": "message-1",
                "threadId": "thread-1",
                "labelIds": ["INBOX"],
                "payload": {
                    "mimeType": "multipart/mixed",
                    "headers": [{"name": "Subject", "value": "A complete message"}],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": "SGVsbG8gZnJvbSB0aGUgYm9keQ=="}},
                        {
                            "filename": "notes.txt",
                            "mimeType": "text/plain",
                            "body": {"attachmentId": "attachment-1", "size": 15},
                        },
                    ],
                },
            })
        if path.endswith("/attachments/attachment-1"):
            return httpx.Response(200, json={"data": "QXR0YWNobWVudCB0ZXh0"})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "history-12"})
        raise AssertionError(f"Unexpected Google request: {request.url}")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        google_service.httpx,
        "AsyncClient",
        lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)),
    )

    records, cursor = await google_service.GoogleWorkspaceOAuthService().fetch_resource("token", "gmail")

    assert cursor == "history-12"
    assert records[0]["body_text"] == "Hello from the body"
    assert records[0]["headers"]["subject"] == "A complete message"
    assert records[0]["attachments"] == [{
        "attachment_id": "attachment-1",
        "filename": "notes.txt",
        "mime_type": "text/plain",
        "content_size": 15,
        "content_text": "Attachment text",
        "content_encoding": "utf-8",
    }]


@pytest.mark.asyncio
async def test_gmail_incremental_sync_uses_history_cursor(monkeypatch):
    requested_history_ids = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/history"):
            requested_history_ids.append(request.url.params.get("startHistoryId"))
            return httpx.Response(200, json={
                "historyId": "history-21",
                "history": [{"messagesAdded": [{"message": {"id": "message-2"}}]}],
            })
        if path.endswith("/messages/message-2"):
            return httpx.Response(200, json={"id": "message-2", "payload": {"mimeType": "text/plain", "body": {"data": "SW5jcmVtZW50YWw="}}})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "history-22"})
        raise AssertionError(f"Unexpected Google request: {request.url}")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(google_service.httpx, "AsyncClient", lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)))

    records, cursor = await google_service.GoogleWorkspaceOAuthService().fetch_resource("token", "gmail", cursor="history-20")

    assert requested_history_ids == ["history-20"]
    assert records[0]["body_text"] == "Incremental"
    assert cursor == "history-22"


@pytest.mark.asyncio
async def test_drive_sync_downloads_binary_and_exports_native_file_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/files"):
            return httpx.Response(200, json={"files": [
                {"id": "text-1", "name": "notes.txt", "mimeType": "text/plain"},
                {"id": "doc-1", "name": "brief", "mimeType": "application/vnd.google-apps.document"},
                {"id": "pdf-1", "name": "terms.pdf", "mimeType": "application/pdf"},
            ]})
        if path.endswith("/files/text-1"):
            assert request.url.params.get("alt") == "media"
            return httpx.Response(200, content=b"plain drive text")
        if path.endswith("/files/doc-1/export"):
            assert request.url.params.get("mimeType") == "text/plain"
            return httpx.Response(200, content=b"exported document")
        if path.endswith("/files/pdf-1"):
            return httpx.Response(200, content=b"%PDF-synchronized")
        if path.endswith("/changes/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "drive-page-31"})
        raise AssertionError(f"Unexpected Google request: {request.url}")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(google_service.httpx, "AsyncClient", lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)))

    records, cursor = await google_service.GoogleWorkspaceOAuthService().fetch_resource("token", "drive")

    by_id = {record["id"]: record for record in records}
    assert by_id["text-1"]["content_text"] == "plain drive text"
    assert by_id["doc-1"]["content_text"] == "exported document"
    assert by_id["pdf-1"]["content_base64"] == "JVBERi1zeW5jaHJvbml6ZWQ="
    assert cursor == "drive-page-31"


@pytest.mark.asyncio
async def test_drive_incremental_sync_uses_changes_cursor(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/changes"):
            assert request.url.params.get("pageToken") == "drive-page-40"
            return httpx.Response(200, json={
                "newStartPageToken": "drive-page-41",
                "changes": [
                    {"fileId": "text-2", "file": {"id": "text-2", "mimeType": "text/plain"}},
                    {"fileId": "deleted-1", "removed": True},
                ],
            })
        if path.endswith("/files/text-2"):
            return httpx.Response(200, content=b"changed content")
        raise AssertionError(f"Unexpected Google request: {request.url}")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(google_service.httpx, "AsyncClient", lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)))

    records, cursor = await google_service.GoogleWorkspaceOAuthService().fetch_resource("token", "drive", cursor="drive-page-40")

    assert records[0]["content_text"] == "changed content"
    assert records[1] == {"id": "deleted-1", "removed": True}
    assert cursor == "drive-page-41"
