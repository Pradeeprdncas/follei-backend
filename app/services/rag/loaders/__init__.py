"""Re-export loaders."""
from app.services.rag.loaders.pdf import extract_pdf_text
from app.services.rag.loaders.docx import extract_docx_text
from app.services.rag.loaders.ppt import extract_ppt_text
from app.services.rag.loaders.email import extract_email_text
from app.services.rag.loaders.text import extract_text_file
from app.services.rag.loaders.spreadsheet import extract_csv_text, extract_xlsx_text
from app.services.rag.loaders.image import extract_image_text

__all__ = ["extract_pdf_text", "extract_docx_text", "extract_ppt_text", "extract_email_text", "extract_text_file", "extract_csv_text", "extract_xlsx_text", "extract_image_text"]
