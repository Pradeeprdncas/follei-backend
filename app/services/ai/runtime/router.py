"""FastAPI Router for AI Runtime health and model endpoints.

Exposes:
- GET /ai/models - Detailed model information
- GET /ai/health - Overall system health
"""
from fastapi import APIRouter
from loguru import logger
from app.services.ai.runtime.runtime_health import get_runtime_health

router = APIRouter(prefix="/ai", tags=["AI Models & Health"])


@router.get("/models")
async def get_ai_models():
    """Get detailed status of all loaded AI models.

    Returns loaded models, versions, device, VRAM, RAM, warm status,
    tokenizer loaded, LoRA loaded, embedding dimensions, etc.
    """
    health = get_runtime_health()
    return await health.get_models_status()


@router.get("/health")
async def get_ai_health():
    """Get overall AI system health.

    Returns overall health, model count, inference ready,
    GPU, VRAM, average latency, memory usage, cache, Redis,
    Qdrant, MCP, Planner, Router.
    """
    health = get_runtime_health()
    return await health.get_system_health()