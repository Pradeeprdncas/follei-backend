"""Source-type chunker registry."""
from pathlib import Path
from app.services.rag.chunking.layout import LayoutAwareChunker
from app.services.rag.chunking.table_aware import TableAwareChunker
from app.services.rag.chunking.turn_aware import TurnAwareChunker

_LAYOUT = LayoutAwareChunker(); _TABLE = TableAwareChunker(); _TURN = TurnAwareChunker()

def strategy_for(source_type: str, filename: str = ""):
    value = f"{source_type} {filename}".lower()
    if any(token in value for token in ("pricing", "catalog", "spec", "table")):
        return _TABLE
    if any(token in value for token in ("email", "eml", "msg", "call", "transcript", "voice")):
        return _TURN
    return _LAYOUT

def is_structured_source(source_type: str, filename: str = "") -> bool:
    value = f"{source_type} {filename}".lower()
    return any(token in value for token in ("crm", "erp", "lms", "api", "structured_record"))

def chunk_document(file_path: str | Path, pages: list[dict], *, metadata: dict | None = None) -> list[dict]:
    path = Path(file_path)
    if is_structured_source(path.suffix.lower().lstrip("."), path.name):
        return []
    strategy = strategy_for(path.suffix.lower().lstrip("."), path.name)
    return strategy.chunk(pages, metadata={**(metadata or {}), "source_type": path.suffix.lower().lstrip(".")})
