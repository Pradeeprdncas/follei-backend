import fitz
from io import BytesIO
from pathlib import Path
import shutil
from PIL import Image
import pytesseract

def extract_pdf_text(file_path):

    doc = fitz.open(file_path)

    pages = []

    current_heading = None

    for page_number in range(len(doc)):

        page = doc[page_number]

        blocks = page.get_text(
            "dict"
        )["blocks"]

        page_text = []

        for block in blocks:

            if "lines" not in block:
                continue

            for line in block["lines"]:

                text = "".join(
                    span["text"]
                    for span in line["spans"]
                ).strip()

                if not text:
                    continue

                font_size = max(
                    span["size"]
                    for span in line["spans"]
                )

                if font_size > 15:

                    current_heading = text

                page_text.append(text)

        extracted = "\n".join(page_text)
        # Scan-only PDFs have no selectable text. Render just that page and
        # use local Tesseract; never OCR a text-rich PDF unnecessarily.
        if not extracted.strip():
            command = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if Path(command).exists():
                pytesseract.pytesseract.tesseract_cmd = command
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                # pytesseract accepts PIL images, NumPy arrays, and paths—not
                # encoded PNG bytes. Decode the rendered pixmap explicitly.
                with Image.open(BytesIO(pix.tobytes("png"))) as image:
                    extracted = pytesseract.image_to_string(image)
        pages.append(
            {
                "page": page_number + 1,
                "heading": current_heading,
                "text": extracted
            }
        )

    return pages
