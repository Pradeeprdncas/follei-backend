"""Read-only aggregation of per-document processing status for the onboarding
loading screen. This derives a status from existing Document/Chunk/
BusinessFactDraft state — it does not add any new processing logic or touch
the ingestion pipeline.
"""
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository

DOCUMENT_STATUSES = ("queued", "parsing", "indexing", "extraction_pending", "extraction_ready", "failed")


def _derive_status(document: Document, has_chunks: bool, has_pending_drafts: bool) -> str:
    if document.status == "failed":
        return "failed"
    if document.status == "indexed" or document.status == "ready":
        if has_pending_drafts:
            return "extraction_pending"
        return "extraction_ready"
    if document.status == "processing":
        return "indexing" if has_chunks else "parsing"
    return "queued"


def list_document_statuses(db: Session, tenant_id) -> list[dict]:
    """Per-document processing status for a tenant, for the onboarding status screen."""
    documents = DocumentRepository(db).get_by_tenant(tenant_id)
    chunk_repo = ChunkRepository(db)
    results = []
    for document in documents:
        chunks = chunk_repo.get_by_document(document.id)
        drafts = db.query(BusinessFactDraft).filter(BusinessFactDraft.document_id == document.id).all()
        has_pending_drafts = any(draft.approval_status == "draft" for draft in drafts)
        results.append({
            "document_id": str(document.id),
            "filename": document.title,
            "status": _derive_status(document, bool(chunks), has_pending_drafts),
            "raw_status": document.status,
            "chunk_count": len(chunks),
            "draft_fact_count": len(drafts),
        })
    return results
