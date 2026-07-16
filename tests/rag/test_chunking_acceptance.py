"""Regression tests for the Phase 2 chunking acceptance gate."""
from pathlib import Path
from uuid import uuid4
import pytest

from app.services.rag.chunking.registry import chunk_document


def _pricing_pdf(path: Path) -> Path:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Pricing\nPlan | Price | Seats\nEnterprise | $30,000 | 100\nStarter | $5,000 | 10")
    doc.save(path)
    doc.close()
    return path


def test_pricing_pdf_keeps_rows_atomic_and_heading_path(tmp_path):
    path = _pricing_pdf(tmp_path / "pricing.pdf")
    import fitz
    pdf = fitz.open(path)
    pages = [{"page": 1, "heading": "Pricing", "text": pdf[0].get_text()}]
    pdf.close()
    chunks = chunk_document(path, pages)
    assert chunks
    assert all(c["chunk_type"] == "table_row" for c in chunks)
    assert all("Plan | Price | Seats" in c["text"] for c in chunks)
    assert all("Pricing" in c["section_path"] for c in chunks)
    assert all(c["approval_status"] == "draft" for c in chunks)


def test_call_thread_preserves_speaker_and_timestamp():
    chunks = chunk_document("call_transcript.eml", [{"page": 1, "text": "[00:01] SDR: Hello\n[00:04] Customer: Need Moodle integration"}])
    assert [c["speaker"] for c in chunks] == ["SDR", "Customer"]
    assert [c["timestamp"] for c in chunks] == ["00:01", "00:04"]


def test_structured_crm_record_bypasses_chunking_and_embedding():
    assert chunk_document("crm_record.json", [{"page": 1, "text": '{"lead_id":"L-1","status":"qualified"}'}]) == []


@pytest.mark.integration

def test_qdrant_payload_contains_heading_path_and_tenant():
    """Requires the local Qdrant service on localhost:6333."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    client = QdrantClient(url="http://localhost:6333", timeout=2)
    collection = "follei_acceptance_test"
    try:
        client.recreate_collection(collection_name=collection, vectors_config=VectorParams(size=3, distance=Distance.COSINE))
    except Exception as exc:
        pytest.skip(f"Qdrant unavailable: {exc}")
    point_id = str(uuid4())
    tenant_id = "7448b124-0844-451a-b4de-9275c0276d65"
    client.upsert(collection_name=collection, points=[PointStruct(id=point_id, vector=[1.0, 0.0, 0.0], payload={"tenant_id": tenant_id, "heading_path": ["Pricing", "Enterprise"], "approval_status": "draft"})])
    points = client.retrieve(collection_name=collection, ids=[point_id], with_payload=True)
    assert points[0].payload["heading_path"] == ["Pricing", "Enterprise"]
    assert points[0].payload["tenant_id"] == tenant_id
    client.delete_collection(collection)
