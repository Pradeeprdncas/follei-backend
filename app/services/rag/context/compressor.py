"""
Chunk-aware context compressor.
"""

import tiktoken
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0

    return len(_encoder.encode(text))


def compress_context(
    chunks,
    max_tokens: int | None = None
):
    """
    Keep highest-ranked chunks until token budget is reached.
    """

    max_t = max_tokens or _settings.MAX_CONTEXT_TOKENS

    selected = []
    total_tokens = 0

    for chunk in chunks:

        text = chunk.text if hasattr(chunk, "text") else str(chunk)

        chunk_tokens = count_tokens(text)

        if total_tokens + chunk_tokens > max_t:
            break

        selected.append(chunk)
        total_tokens += chunk_tokens

    logger.info(
        f"Compressed chunks: {len(chunks)} -> {len(selected)} "
        f"({total_tokens}/{max_t} tokens)"
    )

    return selected


def build_context(
    chunks,
    max_tokens: int | None = None
) -> str:
    """
    Compress then format context.
    """

    selected = compress_chunks(
        chunks,
        max_tokens=max_tokens
    )

    context = "\n\n---\n\n".join(
        chunk.text for chunk in selected
    )

    logger.info(
        f"Final context length: {len(context)} chars"
    )

    return context