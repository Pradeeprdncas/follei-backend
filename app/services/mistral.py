"""Legacy compatibility names backed by Follei's local Qwen runtime.

New code should import ``app.services.ai.local_llm_client`` directly.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from app.services.ai.local_llm_client import complete, stream


async def get_mistral_reply(messages: list[dict]) -> str:
    """Compatibility wrapper; no Mistral or other cloud LLM is called."""
    return await complete(messages, temperature=0.4, max_tokens=800)


async def stream_mistral_reply(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Compatibility wrapper streaming tokens from the local model."""
    async for token in stream(messages, temperature=0.4, max_tokens=800):
        yield token
