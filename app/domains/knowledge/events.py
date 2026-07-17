"""Knowledge domain events."""
def build_document_uploaded_event(document_id: str, tenant_id: str, title: str, source_type: str) -> dict:
    return {"document_id": document_id, "tenant_id": tenant_id, "title": title, "source_type": source_type}


def build_document_processed_event(document_id: str, tenant_id: str, status: str, chunk_count: int) -> dict:
    return {"document_id": document_id, "tenant_id": tenant_id, "status": status, "chunk_count": chunk_count}


def build_entity_extracted_event(entity_id: str, tenant_id: str, entity_type: str, name: str, confidence: float) -> dict:
    return {"entity_id": entity_id, "tenant_id": tenant_id, "type": entity_type, "name": name, "confidence": confidence}
