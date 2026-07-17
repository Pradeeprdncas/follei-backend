"""File parsers for lead import — extract raw content from any document type.

Each parser returns an ExtractedDocument with:
  - text: str          — concatenated text content
  - tables: list       — list of 2D arrays (list[list[str]])
  - metadata: dict     — file info (pages, rows, columns, etc.)
  - pages: int         — page/sheet count
"""
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument
from app.domains.lead_import.parsers.factory import ParserFactory

__all__ = [
    "BaseParser",
    "ExtractedDocument",
    "ParserFactory",
]
