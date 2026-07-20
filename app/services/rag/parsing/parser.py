"""Parser router — dispatches file to correct loader + cleaner."""
from pathlib import Path
from loguru import logger

from app.services.rag.loaders import (
    extract_pdf_text,
    extract_docx_text,
    extract_ppt_text,
    extract_email_text,
    extract_text_file,
    extract_csv_text,
    extract_xlsx_text,
    extract_image_text,
)
from app.services.rag.parsing.cleaner import clean_text, remove_headers_footers


SUPPORTED_EXTENSIONS = {
    ".pdf": extract_pdf_text,
    ".docx": extract_docx_text,
    ".pptx": extract_ppt_text,
    ".ppt": extract_ppt_text,
    ".eml": extract_email_text,
    ".msg": extract_email_text,
    ".txt": extract_text_file,
    ".csv": extract_csv_text,
    ".xlsx": extract_xlsx_text,
    ".png": extract_image_text,
    ".jpg": extract_image_text,
    ".jpeg": extract_image_text,
    ".tif": extract_image_text,
    ".tiff": extract_image_text,
}


def parse_file(file_path: str | Path) -> list[dict]:
    """
    Parse a file into cleaned page/paragraph records.
    Returns list of {"page": int, "text": str, "heading": str | None}.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    loader = SUPPORTED_EXTENSIONS[ext]
    raw_pages = loader(file_path)

    cleaned = []
    for page in raw_pages:
        text = page.get("text", "")
        text = clean_text(text)
        text = remove_headers_footers(text)
        if text:
            cleaned.append({
                "page": page.get("page", 0),
                "text": text,
                "heading": page.get("heading"),
            })

    logger.info(f"Parsed {path.name} → {len(cleaned)} segments")
    return cleaned
