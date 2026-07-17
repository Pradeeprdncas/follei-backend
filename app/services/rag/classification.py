"""Classify a document before selecting its chunking strategy."""
from __future__ import annotations
import json
from pathlib import Path
import httpx
from app.config.settings import get_settings
from loguru import logger

CATEGORIES = {"pricing", "policy", "faq", "sop", "catalog", "transcript", "training", "general"}
_settings = get_settings()


def _heuristic_category(filename: str, text: str, source_type: str) -> str:
    value = f"{filename} {source_type} {text[:3000]}".lower()
    rules = {
        "pricing": ("pricing", "price", "plan", "quote", "rate card"),
        "policy": ("policy", "privacy", "terms", "compliance"),
        "faq": ("faq", "frequently asked", "questions and answers"),
        "sop": ("sop", "standard operating procedure", "procedure", "workflow"),
        "catalog": ("catalog", "catalogue", "sku", "product list", "specification"),
        "transcript": ("transcript", "speaker", "call", "meeting", "email thread"),
        "training": ("training", "lesson", "module", "curriculum", "exercise"),
    }
    for category, terms in rules.items():
        if any(term in value for term in terms):
            return category
    return "general"


async def classify_document(*, filename: str, pages: list[dict], source_type: str) -> str:
    """Return a safe category; an LLM refines the local deterministic fallback."""
    sample = "\n".join(page.get("text", "") for page in pages)[:6000]
    fallback = _heuristic_category(filename, sample, source_type)
    if not _settings.RAG_ENABLE_DOCUMENT_CLASSIFICATION or not _settings.MISTRAL_API_KEY:
        return fallback

    prompt = (
        "Classify this business document into exactly one label: "
        "pricing, policy, faq, sop, catalog, transcript, training, general. "
        "Return JSON only: {\"category\": \"label\"}.\n"
        f"Filename: {Path(filename).name}\nSource type: {source_type}\nContent:\n{sample}"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 32,
                },
            )
            response.raise_for_status()
        category = json.loads(response.json()["choices"][0]["message"]["content"]).get("category", "").lower()
        return category if category in CATEGORIES else fallback
    except Exception as exc:
        logger.warning(f"Document classification fell back to deterministic routing: {exc}")
        return fallback
