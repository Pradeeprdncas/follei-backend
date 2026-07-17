"""Plain text file parser."""

from pathlib import Path
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument


class TextParser(BaseParser):
    """Parse plain text files (.txt) — reads content as-is."""

    async def parse(self, file_path: str) -> ExtractedDocument:
        path = Path(file_path)
        raw = path.read_bytes()

        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        lines = text.splitlines()
        non_empty = [l for l in lines if l.strip()]

        return ExtractedDocument(
            text=text,
            metadata={
                "filename": path.name,
                "lines": len(lines),
                "non_empty_lines": len(non_empty),
                "characters": len(text),
            },
            pages=1,
        )
