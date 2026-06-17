import fitz
from pathlib import Path

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

        pages.append(
            {
                "page": page_number + 1,
                "heading": current_heading,
                "text": "\n".join(page_text)
            }
        )

    return pages