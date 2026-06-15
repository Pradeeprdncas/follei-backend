"""PDF text extraction using pypdf."""
from pathlib import Path
from pypdf import PdfReader
from loguru import logger


def extract_pdf_text(file_path: str | Path) -> list[dict]:
    """
    Extract text page-by-page from a PDF.
    Returns list of {"page": int, "text": str, "heading": str | None}.
    """
    pages = []
    try:
        reader = PdfReader(str(file_path))
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append({
                "page": i,
                "text": text.strip(),
                "heading": None,
            })
        logger.info(f"Extracted {len(pages)} pages from {file_path}")
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        raise
    return pages
