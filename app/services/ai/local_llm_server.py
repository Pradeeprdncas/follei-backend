"""Lifecycle helper for Follei's local llama.cpp generation server."""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import httpx
from loguru import logger

from app.config.settings import get_settings

_settings = get_settings()
_process: subprocess.Popen | None = None


def _workspace_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[3] / path


async def local_llm_is_ready() -> bool:
    health_url = _settings.LOCAL_LLM_BASE_URL.removesuffix("/v1") + "/health"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(health_url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def ensure_local_llm_server() -> bool:
    """Start and pre-warm llama-server when it is not already running.

    Startup is best-effort so the API and its non-AI surfaces remain usable
    when a deployment intentionally hosts the model on another machine.
    """
    global _process
    if await local_llm_is_ready():
        return True
    if not _settings.LOCAL_LLM_AUTO_START or _settings.APP_ENV.lower() == "test":
        return False

    executable = _workspace_path(_settings.LOCAL_LLM_SERVER_PATH)
    model = _workspace_path(_settings.LOCAL_LLM_MODEL_PATH)
    if not executable.exists() or not model.exists():
        logger.warning(
            "Local LLM was not started: executable={} model={}",
            executable,
            model,
        )
        return False

    base = httpx.URL(_settings.LOCAL_LLM_BASE_URL)
    port = base.port or 8081
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    _process = subprocess.Popen(
        [
            str(executable),
            "-m", str(model),
            "--host", base.host or "127.0.0.1",
            "--port", str(port),
            "-ngl", "all",
            "-c", str(_settings.LOCAL_LLM_CONTEXT_SIZE),
            "-fa", "auto",
            "--jinja",
            "--alias", _settings.LOCAL_LLM_MODEL,
            "-np", "1",
            "--metrics",
        ],
        cwd=str(executable.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    deadline = asyncio.get_running_loop().time() + _settings.LOCAL_LLM_STARTUP_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if _process.poll() is not None:
            logger.error("Local llama-server exited with code {}", _process.returncode)
            return False
        if await local_llm_is_ready():
            await _prewarm()
            logger.info("Local response model is ready: {}", _settings.LOCAL_LLM_MODEL)
            return True
        await asyncio.sleep(0.25)
    logger.error("Local llama-server did not become ready before its startup deadline")
    return False


async def _prewarm() -> None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{_settings.LOCAL_LLM_BASE_URL}/chat/completions",
                json={
                    "model": _settings.LOCAL_LLM_MODEL,
                    "messages": [{"role": "user", "content": "Reply only: ready"}],
                    "max_tokens": 2,
                    "temperature": 0,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Local LLM warm-up failed; first request may be slower: {}", exc)
