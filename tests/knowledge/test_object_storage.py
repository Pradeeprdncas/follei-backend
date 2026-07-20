from pathlib import Path

from app.services.knowledge import object_storage


class _FakeS3:
    def __init__(self):
        self.objects = {}

    def head_bucket(self, *, Bucket):
        return {}

    def upload_file(self, filename, bucket, key):
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)
        return {}

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[(bucket, key)])


def test_durable_source_is_used_when_local_staging_file_is_missing(monkeypatch, tmp_path):
    fake = _FakeS3()
    monkeypatch.setattr(object_storage, "_client", fake)
    monkeypatch.setattr(object_storage._settings, "OBJECT_STORAGE_ENABLED", True)
    monkeypatch.setattr(object_storage._settings, "OBJECT_STORAGE_BUCKET", "test-bucket")
    source = tmp_path / "policy.txt"
    source.write_text("Refunds are available for 45 days.", encoding="utf-8")

    key = object_storage.store_source(source, tenant_id="tenant-a", job_id="job-a")
    source.unlink()
    payload = {"file_path": str(source), "object_key": key}

    assert object_storage.source_available(payload) is True
    with object_storage.materialize_source(payload) as restored:
        assert restored.read_text(encoding="utf-8") == "Refunds are available for 45 days."
