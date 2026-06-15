"""Extract metadata per chunk (page, section, heading)."""
from loguru import logger


def extract_chunk_metadata(chunk: dict) -> dict:
    """
    Extract metadata from a chunk dict.
    Returns {"page", "section", "heading", "tags"}.
    """
    return {
        "page": chunk.get("page", 0),
        "section": chunk.get("section"),
        "heading": chunk.get("heading"),
        "tags": chunk.get("tags", []),
    }


def extract_document_metadata(pages: list[dict]) -> dict:
    """
    Extract top-level document metadata from parsed pages.
    Returns {"total_pages", "headings", "sections"}.
    """
    headings = list({p.get("heading") for p in pages if p.get("heading")})
    sections = list({p.get("section") for p in pages if p.get("section")})
    return {
        "total_pages": len(pages),
        "headings": headings,
        "sections": sections,
    }
