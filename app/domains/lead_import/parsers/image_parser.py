"""Image parser using chained OCR (RapidOCR → PaddleOCR → Tesseract) with Pillow preprocessing."""

from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument


class ImageParser(BaseParser):
    """Parse images (PNG, JPG) via chained OCR.

    Tries OCR engines in order: RapidOCR -> PaddleOCR -> pytesseract.
    Each fallback is only attempted if the previous engine fails or returns empty.
    """

    async def parse(self, file_path: str) -> ExtractedDocument:
        path = Path(file_path)
        image = Image.open(file_path)

        text = self._chained_ocr(image)
        ocr_engine = self._last_engine_used
        doc = ExtractedDocument(
            text=text,
            metadata={
                "filename": path.name,
                "format": image.format,
                "size": image.size,
                "mode": image.mode,
                "ocr_engine": ocr_engine,
            },
            pages=1,
        )
        return doc

    _last_engine_used: str = "none"

    @classmethod
    def _preprocess(cls, image: Image.Image) -> Image.Image:
        """Apply Pillow preprocessing to improve OCR accuracy."""
        img = image.convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        return img

    @classmethod
    def _chained_ocr(cls, image: Image.Image) -> str:
        img = cls._preprocess(image)
        text = ""

        # Try 1: RapidOCR
        text = cls._try_rapidocr(img)
        if text and len(text.strip()) > 10:
            cls._last_engine_used = "rapidocr"
            return text

        # Try 2: PaddleOCR
        text = cls._try_paddleocr(img)
        if text and len(text.strip()) > 10:
            cls._last_engine_used = "paddleocr"
            return text

        # Try 3: pytesseract
        text = cls._try_tesseract(img)
        if text and len(text.strip()) > 5:
            cls._last_engine_used = "tesseract"
            return text

        cls._last_engine_used = "none"
        return text or "[OCR: All engines returned empty]"

    @classmethod
    def _try_rapidocr(cls, image: Image.Image) -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR()
            result, _ = engine(image)
            if result:
                lines = [line[1] for line in result if line[1]]
                return "\n".join(lines)
        except Exception:
            pass
        return ""

    @classmethod
    def _try_paddleocr(cls, image: Image.Image) -> str:
        try:
            from paddleocr import PaddleOCR
            engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            result = engine.ocr(image, cls=True)
            if result and result[0]:
                lines = [line[1][0] for line in result[0] if line[1]]
                return "\n".join(lines)
        except Exception:
            pass
        return ""

    @classmethod
    def _try_tesseract(cls, image: Image.Image) -> str:
        try:
            import pytesseract
            return pytesseract.image_to_string(image)
        except ImportError:
            return ""
        except Exception as e:
            error_msg = str(e).lower()
            if "tesseract" in error_msg and "not found" in error_msg:
                return ""
            raise
