"""Build context string from retrieved chunks."""
from app.repositories.chunk import ChunkRepository
from app.config.database import SessionLocal
from loguru import logger


def build_context(chunk_ids: list[str]) -> str:
    """
    Fetch full chunk texts from PostgreSQL and assemble into context string.
    Returns ordered context string.
    """
    db = SessionLocal()
    try:
        repo = ChunkRepository(db)
        chunks = repo.get_by_ids(chunk_ids)

        # Sort by chunk_index to maintain document order
        chunks.sort(key=lambda c: c.chunk_index)

        parts = []
        for chunk in chunks:
            # FIX: Clean, safe inline definition for headings
            heading = f"[{chunk.heading}] " if chunk.heading else ""
            parts.append(f"{heading}Chunk {chunk.chunk_index} (Page {chunk.page}):\n{chunk.text}")

        # FIX: Replaced literal spaces/returns with explicit newline escape markers
        context = "\n\n---\n\n".join(parts)
        
        logger.info(f"Built context: {len(parts)} chunks, {len(context)} chars")
        return context
    finally:
        db.close()