"""Local-only model registry.

The backend may load exactly four models, all through LocalLoader classes.
"""
from typing import Any, Dict

from app.services.ai.model_policy import ALLOWED_MODELS


def _required_files(local_path: str) -> list[str]:
    """Return the list of required files for a model given its local path.

    GGUF models are single files; no config.json, no tokenizer.json.
    Transformers models require config.json and tokenizer.json.
    """
    if local_path.endswith(".gguf"):
        return ["*.gguf"]
    return ["config.json", "tokenizer.json"]


MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    key: {
        "model_type": model.model_type,
        "repo_id": None,
        "local_path": model.local_subpath,
        "required": True,
        "loader": model.loader_name,
        "task": model.model_type,
        "files": _required_files(model.local_subpath),
        "revision": None,
    }
    for key, model in {
        "embedding": ALLOWED_MODELS[("embedding", "nomic-embed-text-v1.5")],
        "query_optimizer": ALLOWED_MODELS[("query_optimizer", "qwen2.5-0.5b")],
        "generator": ALLOWED_MODELS[("generator", "qwen2.5-3b-instruct")],
        "reranker": ALLOWED_MODELS[("reranker", "bge-reranker-base")],
    }.items()
}


def get_model_entry(model_key: str) -> Dict[str, Any]:
    return MODEL_REGISTRY.get(model_key, {})


def get_required_models() -> Dict[str, Dict[str, Any]]:
    return dict(MODEL_REGISTRY)


def get_optional_models() -> Dict[str, Dict[str, Any]]:
    return {}


def get_models_by_type(model_type: str) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in MODEL_REGISTRY.items() if v.get("model_type") == model_type}


def list_all_models() -> Dict[str, Dict[str, Any]]:
    return dict(MODEL_REGISTRY)


def get_model_registry() -> Dict[str, Dict[str, Any]]:
    return MODEL_REGISTRY


def get_fallback_model(model_type: str) -> None:
    return None
