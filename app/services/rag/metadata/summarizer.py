"""Document summarization using Mistral."""
import httpx
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def summarize_text(text: str, max_words: int = 100) -> str:
    """
    Summarize a document using Mistral chat API.
    Returns a short summary string.
    """
    prompt = f"""Summarize the following document in {max_words} words or less. Be concise and capture the main points.

Document:
{text[:8000]}

Summary:"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a helpful summarizer."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 256,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            summary = data["choices"][0]["message"]["content"].strip()
            logger.info(f"Generated summary: {summary[:80]}...")
            return summary
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return ""
