from __future__ import annotations

from types import SimpleNamespace

from kafka.errors import CommitFailedError

from app.workers import google_workspace_worker


class _Consumer:
    def __init__(self):
        self.closed = False

    def __iter__(self):
        return iter([SimpleNamespace(value={"job_id": "job"})])

    def commit(self):
        raise CommitFailedError()

    def close(self):
        self.closed = True


def test_google_worker_survives_commit_rebalance(monkeypatch):
    consumer = _Consumer()

    async def process(_data):
        return None

    monkeypatch.setattr(google_workspace_worker, "ensure_topics", lambda: None)
    monkeypatch.setattr(google_workspace_worker, "get_consumer", lambda *_args: consumer)
    monkeypatch.setattr(google_workspace_worker, "process_google_job", process)

    google_workspace_worker.GoogleWorkspaceWorker().run()

    assert consumer.closed is True
