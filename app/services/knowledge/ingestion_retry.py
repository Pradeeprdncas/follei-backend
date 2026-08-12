"""Shared bounded-retry policy for canonical source-ingestion jobs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IngestionFailure:
    retryable: bool
    job_status: str
    run_status: str
    error: str


class IngestionJobFailed(RuntimeError):
    """Raised after failure state is persisted so the consumer can requeue safely."""

    def __init__(self, failure: IngestionFailure):
        super().__init__(failure.error)
        self.failure = failure


def record_ingestion_failure(
    job: Any,
    run: Any,
    error: Exception,
    *,
    max_attempts: int,
    terminal_run_status: str = "failed",
) -> IngestionFailure:
    """Persistable state transition: retry until the attempt limit, then dead-letter.

    The worker increments ``job.attempt`` before doing provider/network work. A
    failed attempt below ``max_attempts`` is retryable; the final failed attempt
    is terminal and is explicitly marked ``dead_lettered``.
    """
    message = (str(error).strip() or type(error).__name__)[:4000]
    retryable = int(job.attempt or 0) < max_attempts
    job.status = "retrying" if retryable else "dead_lettered"
    job.last_error = message
    run.status = "retrying" if retryable else terminal_run_status
    run.error = message
    return IngestionFailure(
        retryable=retryable,
        job_status=job.status,
        run_status=run.status,
        error=message,
    )


def publish_ingestion_retry(producer: Any, topic: str, data: dict[str, Any], failure: IngestionFailure) -> bool:
    """Requeue the original tenant-bound message only for retryable failures."""
    if not failure.retryable:
        return False
    job_id = data.get("job_id") or data.get("ingestion_job_id")
    if not job_id:
        raise ValueError("Ingestion retry message is missing its job identifier")
    producer.send(topic, key=str(job_id), value=data)
    producer.flush()
    return True
