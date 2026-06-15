"""Hierarchical chunking — preserves heading context."""
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


def hierarchy_chunk(pages: list[dict], chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[dict]:
    """
    Chunk pages while preserving heading hierarchy.
    Returns list of {"text": str, "page": int, "heading": str | None, "section": str | None}.
    """
    from app.services.rag.chunking.semantic import semantic_chunk

    size = chunk_size or _settings.CHUNK_SIZE
    overlap = chunk_overlap or _settings.CHUNK_OVERLAP

    chunks = []
    for page in pages:
        heading = page.get("heading")
        section = heading  # section = heading for now
        page_text = page.get("text", "")
        if not page_text:
            continue

        raw_chunks = semantic_chunk(page_text, size, overlap)
        for i, chunk_text in enumerate(raw_chunks):
            # Prepend heading context if available
            if heading and not chunk_text.startswith(heading):
                chunk_text = f"[{heading}]{chunk_text}"
            chunks.append({
                "text": chunk_text,
                "page": page.get("page", 0),
                "heading": heading,
                "section": section,
            })

    logger.info(f"Hierarchical chunk: {len(pages)} pages → {len(chunks)} chunks")
    return chunks
