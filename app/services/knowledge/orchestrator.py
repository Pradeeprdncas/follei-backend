"""Fixed-order agent context assembly."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.services.rag.retrieval.dense import retrieve_dense
from app.services.knowledge.context_store import get_context


def load_postgres_context(db: Session, tenant_id: str, lead_id: str | None) -> tuple[dict, list[dict]]:
    facts = {"tenant_id": str(tenant_id)}
    relationships: list[dict] = []
    if not lead_id:
        return facts, relationships
    try:
        from app.models.leads.lead import Lead
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    except Exception:
        lead = None
    if lead:
        facts["lead"] = {"id": str(lead.id), "name": " ".join(filter(None, [lead.first_name, lead.last_name])), "email": lead.email, "status": lead.status, "revenue_score": lead.revenue_score, "current_score": lead.current_score, "current_temperature": lead.current_temperature}
        if lead.company:
            relationships.append({"from": str(lead.id), "relation": "belongs_to", "to": lead.company})
    return facts, relationships


async def build_agent_context(*, db: Session, tenant_id: str, query: str, lead_id: str | None = None, customer_id: str | None = None, top_k: int = 5) -> dict:
    """Only public context contract exposed to workforce agents."""
    facts, relationships = load_postgres_context(db, str(tenant_id), lead_id)
    subject_type = "lead" if lead_id else "customer" if customer_id else "tenant"
    subject_id = lead_id or customer_id or str(tenant_id)
    evidence = await retrieve_dense(query, str(tenant_id), top_k=max(1, min(top_k, 10)))
    customer_context = get_context(tenant_id=str(tenant_id), subject_type=subject_type, subject_id=str(subject_id)) or {}
    citations = [{"chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"), "page": item.get("page"), "heading_path": item.get("heading_path", []), "source_type": item.get("source_type"), "approval_status": item.get("approval_status")} for item in evidence]
    return {"facts": facts, "relationships": relationships, "evidence": evidence[:10], "customer_context": customer_context, "citations": citations}
