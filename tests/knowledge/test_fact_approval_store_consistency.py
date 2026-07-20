"""Live-store regression for atomic fact approval plus retryable Qdrant sync."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from qdrant_client.models import PointIdsList, PointStruct

from app.config.database import SessionLocal
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.domain import Policy
from app.models.knowledge.document import Document, DocumentChunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.models.tenancy import Tenant
from app.services.knowledge.outbox import process_sync_event


def test_policy_approval_keeps_postgres_chunk_and_qdrant_consistent_in_one_assertion():
    """A legacy description-only policy must become one approved cross-store fact."""
    tenant_id, document_id, chunk_id, draft_id = uuid4(), uuid4(), uuid4(), uuid4()
    db = SessionLocal()
    qdrant = get_qdrant()
    settings = get_settings()
    collection = settings.QDRANT_COLLECTION_NAME
    vector_config = qdrant.get_collection(collection).config.params.vectors
    vector_size = vector_config.size
    try:
        tenant = Tenant(id=tenant_id, name=f"Approval consistency {tenant_id}")
        document = Document(
            id=document_id,
            tenant_id=tenant_id,
            title="Legacy refund policy.txt",
            source_type="txt",
            source_uri=f"test://{document_id}",
            status="ready",
        )
        chunk = DocumentChunk(
            id=chunk_id,
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_index=0,
            content="The refund window is 45 days from the original purchase date.",
            token_count=12,
            metadata_={
                "heading": "Refund Policy",
                "section_path": ["Policies", "Refund Policy"],
                "tags": ["category:policy", "approval:draft"],
            },
        )
        draft = BusinessFactDraft(
            id=draft_id,
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_id=chunk_id,
            fact_type="policy",
            payload={"description": "The refund window is 45 days from the original purchase date."},
            citation={"document_id": str(document_id), "chunk_id": str(chunk_id), "heading": "Refund Policy"},
            approval_status="draft",
        )
        # These models intentionally expose only FK columns to the fact draft,
        # so establish the live database dependency order explicitly.
        db.add(tenant)
        db.commit()
        db.add(document)
        db.commit()
        db.add(chunk)
        db.commit()
        db.add(draft)
        db.commit()
        qdrant.upsert(
            collection_name=collection,
            wait=True,
            points=[PointStruct(
                id=str(chunk_id),
                vector=[0.0] * vector_size,
                payload={
                    "tenant_id": str(tenant_id),
                    "chunk_id": str(chunk_id),
                    "text": chunk.content,
                    "approval_status": "draft",
                    "tags": ["category:policy", "approval:draft"],
                },
            )],
        )

        token = create_access_token(user_id=uuid4(), tenant_id=tenant_id)
        response = TestClient(app).post(
            f"/knowledge/review/facts/{draft_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={"tenant_id": str(tenant_id), "reviewer": "regression-test"},
        )
        db.expire_all()
        event = db.query(KnowledgeSyncEvent).filter(
            KnowledgeSyncEvent.tenant_id == tenant_id,
            KnowledgeSyncEvent.idempotency_key == f"fact-approved:{draft_id}",
        ).one()
        asyncio.run(process_sync_event(event.id))
        db.expire_all()

        policy = db.query(Policy).filter(Policy.tenant_id == tenant_id).one()
        persisted_chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).one()
        point = qdrant.retrieve(collection_name=collection, ids=[str(chunk_id)], with_payload=True)[0]
        observed = {
            "http_status": response.status_code,
            "operational_policy_body": policy.body,
            "postgres_chunk_approval": "approval:approved" in persisted_chunk.tags,
            "qdrant_approval_status": point.payload.get("approval_status"),
            "qdrant_approved_fact_id": point.payload.get("approved_fact_id"),
            "qdrant_approval_tag": "approval:approved" in point.payload.get("tags", []),
        }
    finally:
        try:
            qdrant.delete(
                collection_name=collection,
                wait=True,
                points_selector=PointIdsList(points=[str(chunk_id)]),
            )
        finally:
            db.rollback()
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                db.delete(tenant)
                db.commit()
            db.close()

    assert observed == {
        "http_status": 200,
        "operational_policy_body": "The refund window is 45 days from the original purchase date.",
        "postgres_chunk_approval": True,
        "qdrant_approval_status": "approved",
        "qdrant_approved_fact_id": str(draft_id),
        "qdrant_approval_tag": True,
    }
