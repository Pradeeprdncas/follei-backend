"""Context compression using tiktoken token counting."""
import tiktoken
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken."""
    enc = tiktoken.get_encoding(model)
    return len(enc.encode(text))


def compress_context(context: str, max_tokens: int | None = None) -> str:
    """
    Trim context to fit within token budget.
    Truncates from the end if over budget.
    """
    max_t = max_tokens or _settings.MAX_CONTEXT_TOKENS
    tokens = count_tokens(context)

    if tokens <= max_t:
        logger.info(f"Context fits: {tokens} tokens <= {max_t}")
        return context

    # Truncate by removing chunks from the end
    parts = context.split("---")
    while parts and count_tokens("---".join(parts)) > max_t:
        parts.pop()

    compressed = "---".join(parts)
    new_tokens = count_tokens(compressed)
    logger.info(f"Compressed context: {tokens} → {new_tokens} tokens ({len(parts)} chunks)")
    return compressed
