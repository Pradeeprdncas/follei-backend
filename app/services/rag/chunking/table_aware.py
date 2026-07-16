"""Table-aware chunking that repeats headers and never splits rows."""
from uuid import uuid4

class TableAwareChunker:
    name = "table_aware"
    def chunk(self, pages: list[dict], *, metadata: dict | None = None) -> list[dict]:
        result = []
        for page in pages:
            lines = [line.strip() for line in page.get("text", "").splitlines() if line.strip()]
            if lines and page.get("heading") and lines[0].lower() == str(page["heading"]).lower():
                lines = lines[1:]
            if not lines:
                continue
            header = lines[0]
            rows = lines[1:] or lines
            for index, row in enumerate(rows):
                text = f"{header}\n{row}"
                result.append({
                    "chunk_id": str(uuid4()), "parent_chunk_id": None,
                    "prev_chunk_id": result[-1]["chunk_id"] if result else None,
                    "next_chunk_id": None, "page": page.get("page", 0),
                    "heading": page.get("heading"),
                    "section_path": [page["heading"]] if page.get("heading") else [],
                    "chunk_index": index, "chunk_type": "table_row",
                    "word_count": len(text.split()), "text": text,
                    "approval_status": "draft", "sensitivity": (metadata or {}).get("sensitivity", "internal"),
                    "source_type": (metadata or {}).get("source_type", "table"),
                    "confidence": float((metadata or {}).get("confidence", 0.0)),
                })
                if len(result) > 1:
                    result[-2]["next_chunk_id"] = result[-1]["chunk_id"]
        return result
