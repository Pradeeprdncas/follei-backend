from types import SimpleNamespace
from uuid import uuid4

from app.workers import indexing_consumer


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def query(self, *_args):
        return _Query(self.rows)

    def close(self):
        self.closed = True


class _Producer:
    def __init__(self):
        self.messages = []
        self.flushed = False

    def send(self, topic, *, key, value):
        self.messages.append((topic, key, value))

    def flush(self):
        self.flushed = True


def test_replay_durable_indexing_jobs_uses_postgres_payload(monkeypatch):
    job_id = uuid4()
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        tenant_id=tenant_id,
        attempt_count=1,
        payload={"filename": "source.txt", "source_metadata": {"ingestion_run_id": str(uuid4())}},
    )
    session = _Session([job])
    producer = _Producer()
    monkeypatch.setattr(indexing_consumer, "SessionLocal", lambda: session)
    monkeypatch.setattr(indexing_consumer, "get_producer", lambda: producer)

    assert indexing_consumer.replay_durable_indexing_jobs() == 1
    assert producer.flushed is True
    assert session.closed is True
    topic, key, payload = producer.messages[0]
    assert topic == indexing_consumer._settings.KAFKA_TOPIC_INDEXING
    assert key == str(job_id)
    assert payload["job_id"] == str(job_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["retry_count"] == 1
    assert payload["filename"] == "source.txt"
