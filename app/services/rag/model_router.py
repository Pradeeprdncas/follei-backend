"""DEPRECATED — VRAM-aware generation router (local-only, no cloud fallback).

WARNING: This module is deprecated. Use app.services.ai.gateway.AIGateway
for all generation. This router is kept temporarily for backward compat.

Cloud (Mistral) fallback removed — local GGUF inference is the only path.
"""
import os
from enum import Enum
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config.settings import get_settings

_settings = get_settings()


class ModelBackend(Enum):
    LOCAL_GGUF = "local_gguf"


@dataclass
class RoutingDecision:
    backend: ModelBackend
    model_name: str
    reason: str


class ModelRouterService:
    """DEPRECATED — local-only model router.

    All generation now goes through AIGateway.
    This class is kept for backward compatibility only.
    """

    def __init__(self, vram_threshold_mb: float = 2048) -> None:
        self._local_model_name = _settings.GENERATOR_MODEL
        self._decisions: list[RoutingDecision] = []
        logger.warning("ModelRouterService is deprecated — use AIGateway instead")

    def select_model(self) -> RoutingDecision:
        decision = RoutingDecision(
            backend=ModelBackend.LOCAL_GGUF,
            model_name=self._local_model_name,
            reason="Local GGUF (deprecated router)",
        )
        self._decisions.append(decision)
        return decision

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.1,
    ) -> str:
        from app.services.ai.gateway import get_ai_gateway
        gateway = get_ai_gateway()
        return await gateway.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.1,
    ):
        from app.services.ai.gateway import get_ai_gateway
        gateway = get_ai_gateway()
        async for token in gateway.generate_stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield token

    def get_routing_log(self) -> list[dict[str, Any]]:
        return [{"backend": "local_gguf", "model": self._local_model_name, "reason": "deprecated"}]

    def clear_routing_log(self) -> None:
        self._decisions.clear()


_router: ModelRouterService | None = None


def get_model_router(vram_threshold_mb: float | None = None) -> ModelRouterService:
    global _router
    if _router is None:
        _router = ModelRouterService(
            vram_threshold_mb=vram_threshold_mb or 2048,
        )
    return _router
