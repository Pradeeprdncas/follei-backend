"""Citation extraction from context chunks."""
from app.repositories.chunk import ChunkRepository
from app.config.database import SessionLocal
from loguru import logger


def extract_citations(chunk_ids: list[str]) -> list[dict]:
    """
    Build citation objects from chunk IDs.
    Returns [{"document_name", "page", "chunk_id"}].
    """
    db = SessionLocal()
    try:
        repo = ChunkRepository(db)
        chunks = repo.get_by_ids(chunk_ids)

        citations = []
        for chunk in chunks:
            doc = chunk.document
            citations.append({
                "document_name": doc.filename if doc else "Unknown",
                "page": chunk.page,
                "chunk_id": chunk.id,
                "heading": chunk.heading,
            })

        logger.info(f"Extracted {len(citations)} citations")
        return citations
    finally:
        db.close()
