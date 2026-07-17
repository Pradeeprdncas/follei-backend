"""PDF parser using pymupdf with automatic OCR fallback for scanned pages."""

from pathlib import Path
from PIL import Image
import io
from pymupdf import Document as PdfDoc
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument
from app.domains.lead_import.parsers.image_parser import ImageParser


class PDFParser(BaseParser):
    """Parse PDF files — extracts text and table-like content page by page.

    Automatically OCRs pages that contain no extractable text (scanned images).
    """

    async def parse(self, file_path: str) -> ExtractedDocument:
        path = Path(file_path)
        doc = PdfDoc(file_path)
        result = ExtractedDocument(metadata={"filename": path.name, "total_pages": len(doc)})
        pages_without_text = 0
        pages_ocr_processed = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            has_text = bool(text and len(text.strip()) >= 20)

            if not has_text:
                pages_without_text += 1
                ocr_text = self._ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    pages_ocr_processed += 1
                    has_text = bool(text.strip())

            tables = self._extract_table_like_content(page, text or "")
            page_doc = ExtractedDocument(
                text=f"--- Page {page_num + 1} ---\n{text}" if text else "",
                tables=tables,
                metadata={
                    "page": page_num + 1,
                    "has_text": has_text,
                    "ocr_applied": not has_text,
                },
                pages=1,
            )
            result.merge(page_doc)

        doc.close()

        result.metadata["pages_without_text"] = pages_without_text
        result.metadata["pages_ocr_processed"] = pages_ocr_processed
        result.metadata["needs_ocr"] = pages_without_text > 0
        result.metadata["ocr_completed"] = pages_ocr_processed > 0
        return result

    @staticmethod
    def _ocr_page(page) -> str:
        """Render a PDF page as an image and run chained OCR."""
        try:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            return ImageParser._chained_ocr(img)
        except Exception:
            return ""

    @staticmethod
    def _extract_table_like_content(page, text: str) -> list[list[list[str]]]:
        """Attempt to extract tables using pymupdf's built-in find_tables."""
        tables = []
        try:
            found = page.find_tables()
            for table in found:
                table_data = []
                for row in table.extract():
                    table_data.append([str(c) if c else "" for c in row])
                if table_data:
                    tables.append(table_data)
        except Exception:
            pass
        return tables
