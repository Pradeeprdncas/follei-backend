"""DOCX text extraction using python-docx."""
from pathlib import Path
from docx import Document as DocxDocument
from loguru import logger


def extract_docx_text(file_path: str | Path) -> list[dict]:
    """
    Extract text paragraph-by-paragraph from a DOCX.
    Returns list of {"page": int, "text": str, "heading": str | None}.
    """
    paragraphs = []
    try:
        doc = DocxDocument(str(file_path))
        current_heading = None
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            # FIX: Safely check if style and style.name exist before calling .startswith()
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                current_heading = text
                
            paragraphs.append({
                "page": 0,
                "text": text,
                "heading": current_heading,
            })
        logger.info(f"Extracted {len(paragraphs)} paragraphs from {file_path}")
    except Exception as e:
        logger.error(f"Failed to parse DOCX {file_path}: {e}")
        raise
    return paragraphs