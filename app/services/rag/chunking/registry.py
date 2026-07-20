"""Source-type chunker registry."""
from pathlib import Path
from app.services.rag.chunking.layout import LayoutAwareChunker
from app.services.rag.chunking.table_aware import TableAwareChunker
from app.services.rag.chunking.turn_aware import TurnAwareChunker
from app.services.rag.chunking.detectors import looks_like_table

_LAYOUT = LayoutAwareChunker()
_TABLE = TableAwareChunker()
_TURN = TurnAwareChunker()


def strategy_for(source_type: str, filename: str = "", *, has_table: bool | None = None):
    value = f"{source_type} {filename}".lower()
    # A category is not a layout.  A prose pricing policy or product catalogue
    # still needs heading-aware chunks; only route to row-preserving chunking
    # when the source actually contains a table.  The None default preserves
    # explicit callers that request a known table-oriented source.
    if has_table is True or (has_table is None and any(token in value for token in ("pricing", "catalog", "spec", "table", "csv", "xlsx"))):
        return _TABLE
    if any(token in value for token in ("email", "eml", "msg", "call", "transcript", "voice")):
        return _TURN
    return _LAYOUT


def is_structured_source(source_type: str, filename: str = "") -> bool:
    value = f"{source_type} {filename}".lower()
    return any(token in value for token in ("crm", "erp", "lms", "api", "structured_record"))


def chunk_document(file_path: str | Path, pages: list[dict], *, metadata: dict | None = None) -> list[dict]:
    path = Path(file_path)
    metadata = metadata or {}
    category = str(metadata.get("category") or "").lower()
    source_type = path.suffix.lower().lstrip(".")
    routing_type = category or source_type
    if is_structured_source(routing_type, path.name):
        return []
    text = "\n".join(str(page.get("text", "")) for page in pages)
    strategy = strategy_for(routing_type, path.name, has_table=looks_like_table(text))
    return strategy.chunk(pages, metadata={**metadata, "source_type": source_type, "category": category or "general"})
