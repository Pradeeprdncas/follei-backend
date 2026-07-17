"""Base parser interface and ExtractedDocument type."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedDocument:
    """Standardized document output from all parsers."""
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: int = 0

    def merge(self, other: "ExtractedDocument") -> "ExtractedDocument":
        """Merge another document into this one (appends text, tables, etc.)."""
        sep = "\n\n" if self.text and other.text else ""
        self.text = self.text + sep + other.text
        self.tables.extend(other.tables)
        self.metadata.update(other.metadata)
        self.pages += other.pages
        return self


class BaseParser(ABC):
    """Abstract base for all file parsers."""

    @abstractmethod
    async def parse(self, file_path: str) -> ExtractedDocument:
        """Parse a file and return extracted document content."""
