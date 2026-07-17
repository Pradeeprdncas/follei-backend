from __future__ import annotations

import re


class LanguageService:
    TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")

    @classmethod
    def detect(cls, text: str, fallback: str = "en") -> str:
        if cls.TAMIL_RE.search(text or ""):
            return "ta"
        return fallback if fallback in {"en", "ta"} else "en"

    @staticmethod
    def locale(language: str) -> str:
        return "ta-IN" if language == "ta" else "en-IN"

    @staticmethod
    def response_instruction(language: str) -> str:
        if language == "ta":
            return "Reply in natural Tamil. Preserve necessary technical terms in English when clearer."
        return "Reply in natural English."
