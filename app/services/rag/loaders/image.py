"""OCR image knowledge sources with local Tesseract."""
from pathlib import Path
import shutil
from PIL import Image
import pytesseract


def extract_image_text(file_path: str | Path) -> list[dict]:
    command = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not Path(command).is_file():
        raise ValueError("Tesseract OCR executable is not installed")
    pytesseract.pytesseract.tesseract_cmd = command
    with Image.open(file_path) as image:
        text = pytesseract.image_to_string(image).strip()
    return [{"page": 1, "heading": Path(file_path).stem, "text": text}] if text else []
