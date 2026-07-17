"""AI Service Layer — Centralized AI inference.

Architecture (local-first, Qdrant-native):
  Caller → AIGateway (single entry for ALL AI ops)
             → ModelManager (owns all models, lazy-loads)
             → Cache (Redis/local)
             → PromptManager (centralized prompts)

Legacy AIRouter (app/services/ai/router.py) still available but new code
should use AIGateway. RAG pipelines still use their own chat_pipeline.
"""
from app.services.ai.model_manager import ModelManager, get_model_manager
from app.services.ai.cache import ResponseCache, get_response_cache
from app.services.ai.router import AIRouter, get_ai_router
from app.services.ai.planner import AIPlanner, get_ai_planner, ExecutionPath
from app.services.ai.mcp_adapter import MCPAdapter, get_mcp_adapter
from app.services.ai.registry import ModelRegistry, BaseModelLoader, get_model_registry
from app.services.ai.gateway import AIGateway, get_ai_gateway
from app.services.ai.prompts import PromptManager, get_prompt_manager

__all__ = [
    "ModelManager",
    "get_model_manager",
    "ResponseCache",
    "get_response_cache",
    "AIRouter",
    "get_ai_router",
    "AIPlanner",
    "get_ai_planner",
    "ExecutionPath",
    "MCPAdapter",
    "get_mcp_adapter",
    "ModelRegistry",
    "BaseModelLoader",
    "get_model_registry",
    "AIGateway",
    "get_ai_gateway",
    "PromptManager",
    "get_prompt_manager",
]


def get_ai_service():
    """Default AI entry point — returns the unified AIGateway."""
    return get_ai_gateway()