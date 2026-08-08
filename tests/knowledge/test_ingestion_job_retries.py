from types import SimpleNamespace

from app.services.knowledge.ingestion_retry import publish_ingestion_retry, record_ingestion_failure


class _Producer:
    def __init__(self):
        self.sent = []
        self.flushed = 0

    def send(self, topic, **kwargs):
        self.sent.append((topic, kwargs))

    def flush(self):
        self.flushed += 1


def test_failed_ingestion_job_is_requeued_before_attempt_limit():
    job = SimpleNamespace(attempt=1, status="running", last_error=None)
    run = SimpleNamespace(status="running", error=None)
    producer = _Producer()

    failure = record_ingestion_failure(job, run, RuntimeError("provider unavailable"), max_attempts=3)
    published = publish_ingestion_retry(
        producer,
        "website-ingestion",
        {"job_id": "job-1", "tenant_id": "tenant-1"},
        failure,
    )

    assert failure.retryable is True
    assert job.status == run.status == "retrying"
    assert job.last_error == run.error == "provider unavailable"
    assert published is True
    assert producer.sent == [
        ("website-ingestion", {"key": "job-1", "value": {"job_id": "job-1", "tenant_id": "tenant-1"}})
    ]
    assert producer.flushed == 1


def test_failed_ingestion_job_is_dead_lettered_at_attempt_limit():
    job = SimpleNamespace(attempt=3, status="running", last_error=None)
    run = SimpleNamespace(status="running", error=None)
    producer = _Producer()

    failure = record_ingestion_failure(job, run, RuntimeError("permanent failure"), max_attempts=3)
    published = publish_ingestion_retry(
        producer,
        "website-ingestion",
        {"job_id": "job-1", "tenant_id": "tenant-1"},
        failure,
    )

    assert failure.retryable is False
    assert job.status == "dead_lettered"
    assert run.status == "failed"
    assert published is False
    assert producer.sent == []
    assert producer.flushed == 0
