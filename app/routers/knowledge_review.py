"""Minimal tenant-scoped draft review API."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings

router = APIRouter(prefix="/knowledge/review", tags=["knowledge-review"])
_settings = get_settings()

class ReviewAction(BaseModel):
    tenant_id: str
    reviewer: str = Field(default="human")
    reason: str | None = None

@router.get("/drafts")
def list_drafts(tenant_id: str, limit: int = 50):
    points, _ = get_qdrant().scroll(collection_name=_settings.QDRANT_COLLECTION_NAME, scroll_filter={"must": [{"key": "tenant_id", "match": {"value": tenant_id}}, {"key": "approval_status", "match": {"value": "draft"}}]}, limit=max(1, min(limit, 200)), with_payload=True)
    return [{"chunk_id": str(p.id), "tenant_id": tenant_id, **(p.payload or {})} for p in points]

@router.post("/{chunk_id}/approve")
def approve_draft(chunk_id: str, action: ReviewAction):
    return _set_status(chunk_id, action, "approved")

@router.post("/{chunk_id}/reject")
def reject_draft(chunk_id: str, action: ReviewAction):
    return _set_status(chunk_id, action, "rejected")

def _set_status(chunk_id: str, action: ReviewAction, status: str):
    client = get_qdrant()
    points = client.retrieve(collection_name=_settings.QDRANT_COLLECTION_NAME, ids=[chunk_id], with_payload=True)
    if not points or (points[0].payload or {}).get("tenant_id") != action.tenant_id:
        raise HTTPException(status_code=404, detail="Draft not found for tenant")
    payload = {"approval_status": status, "reviewer": action.reviewer}
    if action.reason:
        payload["review_reason"] = action.reason
    client.set_payload(collection_name=_settings.QDRANT_COLLECTION_NAME, points=[chunk_id], payload=payload)
    return {"chunk_id": chunk_id, "tenant_id": action.tenant_id, "approval_status": status, "reviewer": action.reviewer}
