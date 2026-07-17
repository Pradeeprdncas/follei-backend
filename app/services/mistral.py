"""CLOUD API — DISABLED BY DEFAULT.

Mistral API client. Only available when ENABLE_CLOUD_FALLBACK=true.
Otherwise raises RuntimeError on any call.

Local inference (GGUF via llama.cpp) is the default. This file exists
for legacy compatibility only.
"""
import os
import json
from typing import AsyncGenerator
from loguru import logger

from app.config.settings import get_settings


_ENABLED = os.getenv("ENABLE_CLOUD_FALLBACK", "false").strip().lower() in ("true", "1", "yes")


def _require_enabled():
    if not _ENABLED:
        raise RuntimeError(
            "Mistral API is disabled. Set ENABLE_CLOUD_FALLBACK=true to enable, "
            "or use local inference via AIGateway."
        )


async def get_mistral_reply(messages: list[dict]) -> str:
    _require_enabled()
    import httpx
    from fastapi import HTTPException, status

    api_key = (get_settings().MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY missing")

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": (os.getenv("MISTRAL_MODEL") or "mistral-large-latest").strip(),
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Mistral API request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Mistral API error {response.status_code}")

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Unexpected Mistral response") from exc


async def stream_mistral_reply(messages: list[dict]) -> AsyncGenerator[str, None]:
    _require_enabled()
    import httpx
    from fastapi import HTTPException, status

    api_key = (get_settings().MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY missing")

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": (os.getenv("MISTRAL_MODEL") or "mistral-large-latest").strip(),
        "messages": messages,
        "stream": True,
        "temperature": 0.4,
        "max_tokens": 800,
    }

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Mistral API error {response.status_code}")
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line.replace("data: ", "")
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except Exception:
                        continue
