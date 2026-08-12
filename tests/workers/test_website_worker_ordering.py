from unittest.mock import Mock

from app.workers import website_ingestion_worker


def test_prepare_index_job_does_not_publish_before_caller_commits(monkeypatch, tmp_path):
    producer = Mock()
    monkeypatch.setattr(website_ingestion_worker, "get_producer", lambda: producer)
    monkeypatch.setattr(website_ingestion_worker, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(website_ingestion_worker, "store_source", lambda *_args, **_kwargs: "object-key")
    db = Mock()

    job_id, payload = website_ingestion_worker._prepare_index_job(
        db,
        tenant_id="11111111-1111-1111-1111-111111111111",
        source_id="22222222-2222-2222-2222-222222222222",
        run_id="33333333-3333-3333-3333-333333333333",
        record={"url": "https://example.com/pricing", "title": "Pricing", "text": "$29 per month"},
        category=None,
    )

    assert job_id == payload["job_id"]
    db.add.assert_called_once()
    producer.send.assert_not_called()
    producer.flush.assert_not_called()
