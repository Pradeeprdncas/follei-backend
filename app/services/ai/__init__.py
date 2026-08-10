"""AI Service Layer — lazily loaded to keep the core API lightweight.

Architecture (local-first, Qdrant-native):
  Caller → AIGateway (single entry for ALL AI ops)
             → ModelManager (owns all models, lazy-loads)
             → Cache (Redis/local)
             → PromptManager (centralized prompts)

Legacy AIRouter (app/services/ai/router.py) still available but new code
should use AIGateway. RAG pipelines still use their own chat_pipeline.
Importing ``app.services.ai.local_llm_client`` used to execute this package file
and eagerly import torch/transformers through ModelManager. That made ordinary
API, OAuth, and ingestion startup pay for optional local-model features. Public
exports remain compatible, but are resolved only when requested.
"""
from importlib import import_module


_LAZY_EXPORTS = {
    "ModelManager": ("app.services.ai.model_manager", "ModelManager"),
    "get_model_manager": ("app.services.ai.model_manager", "get_model_manager"),
    "ResponseCache": ("app.services.ai.cache", "ResponseCache"),
    "get_response_cache": ("app.services.ai.cache", "get_response_cache"),
    "AIRouter": ("app.services.ai.router", "AIRouter"),
    "get_ai_router": ("app.services.ai.router", "get_ai_router"),
    "AIPlanner": ("app.services.ai.planner", "AIPlanner"),
    "get_ai_planner": ("app.services.ai.planner", "get_ai_planner"),
    "ExecutionPath": ("app.services.ai.planner", "ExecutionPath"),
    "MCPAdapter": ("app.services.ai.mcp_adapter", "MCPAdapter"),
    "get_mcp_adapter": ("app.services.ai.mcp_adapter", "get_mcp_adapter"),
    "ModelRegistry": ("app.services.ai.registry", "ModelRegistry"),
    "BaseModelLoader": ("app.services.ai.registry", "BaseModelLoader"),
    "get_model_registry": ("app.services.ai.registry", "get_model_registry"),
    "AIGateway": ("app.services.ai.gateway", "AIGateway"),
    "get_ai_gateway": ("app.services.ai.gateway", "get_ai_gateway"),
    "PromptManager": ("app.services.ai.prompts", "PromptManager"),
    "get_prompt_manager": ("app.services.ai.prompts", "get_prompt_manager"),
}

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
    "PromptManager", "get_prompt_manager",
]


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    value = getattr(import_module(target[0]), target[1])
    globals()[name] = value
    return value


def get_ai_service():
    """Default AI entry point — returns the unified AIGateway."""
    return __getattr__("get_ai_router")()
