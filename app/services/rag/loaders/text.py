"""Plain-text extraction for tenant-uploaded .txt knowledge sources."""
from pathlib import Path


def extract_text_file(file_path: str | Path) -> list[dict]:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace").strip()
    return [{"page": 0, "text": text, "heading": None}] if text else []
