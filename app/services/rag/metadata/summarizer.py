"""Document summarization using Follei's local response model."""
from app.services.ai.local_llm_client import complete
from loguru import logger

async def summarize_text(text: str, max_words: int = 100) -> str:
    """
    Summarize a document using the local Qwen model.
    Returns a short summary string.
    """
    prompt = f"""Summarize the following document in {max_words} words or less. Be concise and capture the main points.

Document:
{text[:8000]}

Summary:"""

    try:
        summary = await complete(
            [
                {"role": "system", "content": "You are a helpful summarizer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.3,
        )
        logger.info(f"Generated summary: {summary[:80]}...")
        return summary
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return ""
