from __future__ import annotations

import re


class LanguageService:
    TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
    ISO3_TO_ISO2 = {
        "eng": "en", "tam": "ta", "hin": "hi", "tel": "te", "mal": "ml",
        "kan": "kn", "mar": "mr", "ben": "bn", "guj": "gu", "pan": "pa",
        "spa": "es", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de",
        "por": "pt", "ara": "ar", "zho": "zh", "chi": "zh", "jpn": "ja",
        "kor": "ko", "rus": "ru",
    }

    @classmethod
    def normalize(cls, language: str | None, fallback: str = "en") -> str:
        code = str(language or "").strip().lower().replace("_", "-").split("-", 1)[0]
        return cls.ISO3_TO_ISO2.get(code, code or fallback)

    @classmethod
    def detect(cls, text: str, fallback: str = "en") -> str:
        if cls.TAMIL_RE.search(text or ""):
            return "ta"
        return fallback if fallback in {"en", "ta"} else "en"

    @staticmethod
    def locale(language: str) -> str:
        normalized = LanguageService.normalize(language)
        return "ta-IN" if normalized == "ta" else "en-IN"

    @staticmethod
    def response_instruction(language: str) -> str:
        if LanguageService.normalize(language) == "ta":
            return "Reply in natural Tamil. Preserve necessary technical terms in English when clearer."
        return "Reply in natural English."
