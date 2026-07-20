"""S3-compatible durable source storage with local staging fallback."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile

from app.config.settings import get_settings

_settings = get_settings()
_client = None


def enabled() -> bool:
    return bool(_settings.OBJECT_STORAGE_ENABLED)


def _get_client():
    global _client
    if _client is None:
        import boto3
        _client = boto3.client(
            "s3",
            endpoint_url=_settings.OBJECT_STORAGE_ENDPOINT_URL,
            aws_access_key_id=_settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=_settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=_settings.OBJECT_STORAGE_REGION,
        )
    return _client


def ensure_bucket() -> None:
    if not enabled():
        return
    client = _get_client()
    try:
        client.head_bucket(Bucket=_settings.OBJECT_STORAGE_BUCKET)
    except Exception:
        client.create_bucket(Bucket=_settings.OBJECT_STORAGE_BUCKET)


def store_source(local_path: str | Path, *, tenant_id: str, job_id: str) -> str | None:
    if not enabled():
        return None
    path = Path(local_path)
    key = f"tenants/{tenant_id}/sources/{job_id}{path.suffix.lower()}"
    ensure_bucket()
    _get_client().upload_file(str(path), _settings.OBJECT_STORAGE_BUCKET, key)
    return key


def source_available(payload: dict) -> bool:
    local_path = payload.get("file_path")
    if local_path and Path(local_path).is_file():
        return True
    key = payload.get("object_key")
    if not enabled() or not key:
        return False
    try:
        _get_client().head_object(Bucket=_settings.OBJECT_STORAGE_BUCKET, Key=str(key))
        return True
    except Exception:
        return False


@contextmanager
def materialize_source(payload: dict):
    local_path = payload.get("file_path")
    if local_path and Path(local_path).is_file():
        yield Path(local_path)
        return
    key = payload.get("object_key")
    if not enabled() or not key:
        raise FileNotFoundError(f"Source is unavailable locally and has no durable object: {local_path}")
    suffix = Path(str(local_path or key)).suffix
    with tempfile.TemporaryDirectory(prefix="follei-source-") as temp_dir:
        path = Path(temp_dir) / f"source{suffix}"
        _get_client().download_file(_settings.OBJECT_STORAGE_BUCKET, str(key), str(path))
        yield path
