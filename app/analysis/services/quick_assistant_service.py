from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo


class QuickAssistantService:
    """Low-latency intent answers for Google-Assistant-style response time."""

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    @classmethod
    def maybe_answer(cls, prompt: str) -> str | None:
        text = cls.normalize(prompt)
        if not text:
            return "Please say that again."

        sales_terms = ("buy", "pricing", "price", "demo", "budget", "implementation", "timeline", "automation")
        hot_terms = ("ready to buy", "this month", "this quarter", "approved", "decision maker", "urgent")
        if any(term in text for term in sales_terms):
            if any(term in text for term in hot_terms):
                return (
                    "This is a hot lead. I can help with pricing, a live demo, security details, "
                    "and implementation timeline. Next step: book the demo and prepare a proposal."
                )
            return (
                "This looks like a warm lead. I can share the value summary, pricing range, "
                "and a relevant case study, then offer a short demo."
            )

        if text in {"hi", "hello", "hey", "hai"} or text.startswith(("hi ", "hello ", "hey ")):
            return "Hi. How can I help you?"

        if any(phrase in text for phrase in ("who are you", "what are you", "your name")):
            return "I am your enterprise AI assistant. I can answer questions, help with writing, and respond by voice."

        if text in {"who is vijay", "who is thalapathy vijay", "vijay"}:
            return "Vijay, also known as Thalapathy Vijay, is a popular Indian actor and politician from Tamil Nadu."

        if text in {"who is dhoni", "who is ms dhoni", "who is mahendra singh dhoni", "dhoni"}:
            return "MS Dhoni is a former Indian cricket captain, wicketkeeper-batter, and one of India's most successful cricket leaders."

        if any(phrase in text for phrase in ("what time", "current time", "time now", "time is it")):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return f"The time is {now.strftime('%I:%M %p')}."

        if any(phrase in text for phrase in ("today date", "current date", "what date", "date today")):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return f"Today is {now.strftime('%A, %d %B %Y')}."

        if text in {"thank you", "thanks", "thank you so much"}:
            return "You are welcome."

        if "what is ai" in text or "artificial intelligence" in text:
            return "Artificial intelligence is technology that helps computers understand, reason, and make decisions like a human for specific tasks."

        if "what is machine learning" in text or "machine learning" == text:
            return "Machine learning is a part of AI where systems learn patterns from data and improve predictions without being manually programmed for every case."

        if "what is rag" in text:
            return "RAG means Retrieval-Augmented Generation. It searches relevant documents first, then uses them to generate a more accurate answer."

        if "what is redis" in text:
            return "Redis is a fast in-memory database. In this project it stores short-term conversation memory."

        if "what is chromadb" in text or "what is chroma" in text:
            return "ChromaDB is a vector database. It stores embeddings and helps retrieve relevant documents for RAG."

        if "what is sentiment" in text:
            return "Sentiment analysis detects whether text sounds positive, negative, or neutral."

        if "leave letter" in text:
            return (
                "Subject: Leave Request\n\n"
                "Dear Sir/Madam,\n\n"
                "I request leave from [start date] to [end date] due to [reason]. "
                "I will complete or hand over my pending work before my leave.\n\n"
                "Thank you.\n[Your Name]"
            )

        return None

    @classmethod
    def timeout_fallback(cls, prompt: str) -> str:
        text = prompt.strip()
        if not text:
            return "Please say that again."
        return (
            "I heard you, but I need a little more time for a detailed answer. "
            "Please ask in one short sentence for instant response."
        )
