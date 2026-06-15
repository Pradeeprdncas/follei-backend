"""Re-export loaders."""
from app.services.rag.loaders.pdf import extract_pdf_text
from app.services.rag.loaders.docx import extract_docx_text
from app.services.rag.loaders.ppt import extract_ppt_text
from app.services.rag.loaders.email import extract_email_text

__all__ = ["extract_pdf_text", "extract_docx_text", "extract_ppt_text", "extract_email_text"]
