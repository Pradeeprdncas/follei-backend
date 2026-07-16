"""Central approval policy for knowledge retrieval."""
_APPROVAL_TERMS = ("pricing", "price", "policy", "policies", "plan", "plans", "faq", "frequently asked", "sla", "terms")

def requires_approval(query: str, category: str | None = None) -> bool:
    value = f"{query} {category or ''}".lower()
    return any(term in value for term in _APPROVAL_TERMS)

def approved_filter(tenant_id: str, *, require_approved: bool) -> dict:
    must = [{"key": "tenant_id", "match": {"value": str(tenant_id)}}]
    if require_approved:
        must.append({"key": "approval_status", "match": {"value": "approved"}})
    return {"must": must}
