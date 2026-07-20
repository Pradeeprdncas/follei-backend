"""Central approval policy for knowledge retrieval."""
_APPROVAL_TERMS = ("pricing", "price", "policy", "policies", "plan", "plans", "faq", "frequently asked", "sla", "terms")

def requires_approval(query: str, category: str | None = None) -> bool:
    value = f"{query} {category or ''}".lower()
    return any(term in value for term in _APPROVAL_TERMS)

def approved_filter(tenant_id: str, *, require_approved: bool = True) -> dict:
    """Return the mandatory tenant + approval boundary for document evidence.

    ``require_approved`` is retained for compatibility with older callers, but
    can no longer weaken the boundary. Draft evidence belongs in review APIs,
    never in worker/chat retrieval.
    """
    return {"must": [
        {"key": "tenant_id", "match": {"value": str(tenant_id)}},
        {"key": "approval_status", "match": {"value": "approved"}},
    ]}


# Postgres document_chunks has no dedicated approval_status column; approval state
# is encoded as an "approval:<status>" string inside the chunk's tags array (see
# app/services/rag/pipelines/indexing.py). This is the single source of truth for
# reading that state back out on the Postgres retrieval paths (BM25, neighbor
# expansion) so they agree with Qdrant's approval_status filtering instead of
# inventing a second policy.
def chunk_tags_approved(tags) -> bool:
    """True only if the chunk's Postgres tags explicitly mark it approved."""
    return "approval:approved" in (tags or [])


def approval_tag_for(status: str) -> str:
    return f"approval:{status}"
