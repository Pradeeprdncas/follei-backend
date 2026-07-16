"""Layout-aware strategy for PDF/DOCX page records."""
from app.services.rag.chunking.hierarchy import hierarchy_chunk

class LayoutAwareChunker:
    name = "layout_aware"
    def chunk(self, pages: list[dict], *, metadata: dict | None = None) -> list[dict]:
        chunks = hierarchy_chunk(pages)
        for chunk in chunks:
            path = chunk.get("section_path") or []
            if not path and chunk.get("heading"):
                path = [chunk["heading"]]
            chunk["section_path"] = path
            chunk["approval_status"] = "draft"
            chunk["sensitivity"] = (metadata or {}).get("sensitivity", "internal")
            chunk["source_type"] = (metadata or {}).get("source_type", "document")
            chunk["confidence"] = float((metadata or {}).get("confidence", 0.0))
        return chunks
