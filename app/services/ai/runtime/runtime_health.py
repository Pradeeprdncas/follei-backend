"""Runtime Health - Model and system health endpoints.

Exposes:
- GET /ai/models - Detailed model information
- GET /ai/health - Overall system health
"""
import time
from typing import Dict, Any, List, Optional
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.runtime.runtime_verifier import get_runtime_verifier

_settings = get_settings()


class RuntimeHealth:
    """Provides health and model status information."""

    def __init__(self):
        self._start_time = time.time()

    async def get_models_status(self) -> Dict[str, Any]:
        """Get detailed status of all loaded models.

        Returns:
            Dict with model versions, device, VRAM, RAM, warm status, etc.
        """
        from app.services.ai.model_manager import get_model_manager
        from app.services.ai.model_warmup import get_model_warmup
        from app.services.ai.runtime.runtime_verifier import get_runtime_verifier
        from app.services.ai.registry import get_model_registry

        manager = get_model_manager()
        warmup = get_model_warmup()
        verifier = get_runtime_verifier()

        loaded_models = manager.get_loaded_models()
        warmup_times = warmup.get_warmup_times()

        device_info = self._get_device_info()
        memory_info = self._get_memory_info()

        model_details = {}
        for model_key, info in loaded_models.items():
            model_type = info.get("type", "?")
            model_name = info.get("name", "?")
            warm_key = f"{model_type}:{model_name}"
            model_details[model_key] = {
                "type": model_type,
                "name": model_name,
                "loaded": True,
                "warmup_time_s": warmup_times.get(warm_key, None),
                "device": device_info.get("device", "?"),
            }

        # Add generator-specific info
        generator_info = manager.is_model_loaded("generator", _settings.GENERATOR_MODEL)
        generator_details = {}
        if generator_info:
            gen_key = f"generator:{_settings.GENERATOR_MODEL}"
            gen_data = manager._models.get(gen_key, {})
            gen_model = gen_data.get("model")
            gen_tokenizer = gen_data.get("tokenizer")
            generator_details = {
                "loaded": True,
                "has_tokenizer": gen_tokenizer is not None,
                "has_lora": (
                    hasattr(gen_model, "peft_config") if gen_model else False
                ),
            }
        else:
            generator_details = {"loaded": False}

        # Get embedding dimensions
        embed_key = f"embedding:{_settings.EMBED_MODEL}"
        embed_data = manager._models.get(embed_key, {})
        embed_loader = embed_data.get("loader")
        embed_dim = None
        if embed_loader and hasattr(embed_loader, "_model"):
            try:
                st_model = embed_loader._model
                embed_dim = st_model.get_sentence_embedding_dimension()
            except Exception:
                pass

        return {
            "models": model_details,
            "generator": generator_details,
            "embedding_dimensions": embed_dim,
            "device": device_info,
            "memory": memory_info,
            "warm_status": warmup.is_warmed_up(),
            "runtime_ready": verifier.is_ready,
            "config": {
                "embedding": _settings.EMBED_MODEL,
                "classifier": _settings.INTENT_MODEL,
                "generator": _settings.GENERATOR_MODEL,
                "summarizer": _settings.SUMMARY_MODEL,
                "reranker": _settings.RERANK_MODEL,
                "query_optimizer": _settings.QUERY_MODEL,
                "lora": _settings.LORA_MODEL,
            },
        }

    async def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health.

        Returns:
            Dict with overall health, model count, inference readiness,
            GPU, VRAM, latency, memory, cache, Redis, Qdrant, MCP, Planner, Router
        """
        from app.services.ai.model_manager import get_model_manager
        from app.services.ai.model_warmup import get_model_warmup
        from app.services.ai.router import get_ai_router

        manager = get_model_manager()
        warmup = get_model_warmup()
        router = get_ai_router()

        loaded_models = manager.get_loaded_models()
        warmup_times = warmup.get_warmup_times()
        avg_latency = (
            sum(warmup_times.values()) / len(warmup_times)
            if warmup_times
            else None
        )

        device_info = self._get_device_info()
        memory_info = self._get_memory_info()

        # Check services status
        services_status = await self._check_services()

        health = {
            "overall": "healthy" if warmup.is_warmed_up() else "degraded",
            "uptime_s": time.time() - self._start_time,
            "model_count": len(loaded_models),
            "inference_ready": warmup.is_warmed_up(),
            "device": device_info,
            "memory": memory_info,
            "average_warmup_latency_s": avg_latency,
            "services": services_status,
            "cache_status": self._get_cache_status(),
        }

        # Add an overall health check
        if not warmup.is_warmed_up() and len(loaded_models) == 0:
            health["overall"] = "unhealthy"

        return health

    def _get_device_info(self) -> Dict[str, Any]:
        """Get device information."""
        info = {"device": "cpu", "cuda_available": False, "cuda_device": None}
        try:
            import torch

            if torch.cuda.is_available():
                info["device"] = "cuda"
                info["cuda_available"] = True
                info["cuda_device"] = torch.cuda.get_device_name(0)
                info["cuda_count"] = torch.cuda.device_count()
        except ImportError:
            pass
        return info

    def _get_memory_info(self) -> Dict[str, Any]:
        """Get memory usage information."""
        info = {"ram_gb": 0, "ram_percent": 0, "vram_gb": 0, "vram_percent": 0}
        try:
            import psutil

            mem = psutil.virtual_memory()
            info["ram_gb"] = round(mem.total / (1024**3), 2)
            info["ram_percent"] = mem.percent
        except ImportError:
            pass

        try:
            import torch

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated(0) / (1024**3)
                total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                info["vram_gb"] = round(allocated, 2)
                info["vram_percent"] = round((allocated / total) * 100, 1) if total > 0 else 0
        except ImportError:
            pass

        return info

    async def _check_services(self) -> Dict[str, str]:
        """Check status of connected services."""
        status = {}

        # Redis check
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(_settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            status["redis"] = "connected"
            await r.aclose()
        except Exception:
            status["redis"] = "disconnected"

        # Qdrant check
        try:
            from qdrant_client import AsyncQdrantClient
            qdrant = AsyncQdrantClient(
                url=_settings.QDRANT_URL,
                api_key=_settings.QDRANT_API_KEY,
            )
            await qdrant.get_collections()
            status["qdrant"] = "connected"
            await qdrant.close()
        except Exception:
            status["qdrant"] = "disconnected"

        # MCP check
        try:
            from app.services.ai.mcp_adapter import get_mcp_adapter
            mcp = get_mcp_adapter()
            status["mcp"] = (
                "initialized" if mcp._initialized else "not_initialized"
            )
        except Exception:
            status["mcp"] = "unavailable"

        # Local-only architecture — no cloud fallback needed
        status["cloud_fallback"] = "disabled (local-only mode)"
        status["local_inference"] = "active"

        # Planner and Router are always available
        status["planner"] = "active"
        status["router"] = "active"
        status["rag"] = "configured"

        return status

    def _get_cache_status(self) -> Dict[str, Any]:
        """Get cache status information."""
        try:
            from app.services.ai.cache import get_response_cache
            cache = get_response_cache()
            return {
                "enabled": True,
                "stats": cache.get_stats(),
            }
        except Exception:
            return {"enabled": False, "stats": {}}


# Singleton
_health: Optional["RuntimeHealth"] = None


def get_runtime_health() -> RuntimeHealth:
    """Get or create singleton runtime health."""
    global _health
    if _health is None:
        _health = RuntimeHealth()
    return _health