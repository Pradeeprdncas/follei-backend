"""Local-only AI model policy.

This module is the single allowlist for production model loading.  Any
attempt to load a model outside this list must fail clearly.
"""

from dataclasses import dataclass


class DisallowedModelError(RuntimeError):
    """Raised when code attempts to use a non-approved model."""


@dataclass(frozen=True)
class AllowedModel:
    model_type: str
    model_name: str
    loader_name: str
    local_subpath: str


ALLOWED_MODELS: dict[tuple[str, str], AllowedModel] = {
    ("embedding", "nomic-embed-text-v1.5"): AllowedModel(
        model_type="embedding",
        model_name="nomic-embed-text-v1.5",
        loader_name="LocalEmbeddingLoader",
        local_subpath="embeddings/nomic-embed-text-v1.5",
    ),
    ("query_optimizer", "qwen2.5-0.5b"): AllowedModel(
        model_type="query_optimizer",
        model_name="qwen2.5-0.5b",
        loader_name="LocalGGUFModelLoader",
        local_subpath="gguf/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    ),
    ("generator", "qwen2.5-3b-instruct"): AllowedModel(
        model_type="generator",
        model_name="qwen2.5-3b-instruct",
        loader_name="LocalGGUFModelLoader",
        local_subpath="gguf/qwen2.5-3b-instruct-q4_k_m.gguf",
    ),
    ("generator", "qwen2.5-0.5b"): AllowedModel(
        model_type="generator",
        model_name="qwen2.5-0.5b",
        loader_name="LocalGGUFModelLoader",
        local_subpath="gguf/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    ),
    ("reranker", "bge-reranker-base"): AllowedModel(
        model_type="reranker",
        model_name="bge-reranker-base",
        loader_name="LocalRerankerLoader",
        local_subpath="rerankers/bge-reranker-base",
    ),
    ("classifier", "ModernBERT-base"): AllowedModel(
        model_type="classifier",
        model_name="ModernBERT-base",
        loader_name="LocalClassifierLoader",
        local_subpath="classifiers/ModernBERT-base",
    ),
    ("summarizer", "smollm2-360m"): AllowedModel(
        model_type="summarizer",
        model_name="smollm2-360m",
        loader_name="LocalSummarizerLoader",
        local_subpath="llms/smollm2-360m",
    ),
    ("verifier", "qwen2.5-0.5b"): AllowedModel(
        model_type="verifier",
        model_name="qwen2.5-0.5b",
        loader_name="LocalVerifierLoader",
        local_subpath="llms/qwen2.5-0.5b",
    ),
    ("planner", "qwen2.5-0.5b"): AllowedModel(
        model_type="planner",
        model_name="qwen2.5-0.5b",
        loader_name="LocalPlannerLoader",
        local_subpath="llms/qwen2.5-0.5b",
    ),
}


def require_allowed_model(model_type: str, model_name: str) -> AllowedModel:
    model = ALLOWED_MODELS.get((model_type, model_name))
    if model is None:
        allowed = ", ".join(f"{t}:{n}" for t, n in sorted(ALLOWED_MODELS))
        raise DisallowedModelError(
            f"Model '{model_type}:{model_name}' is not allowed. "
            f"Allowed local models: {allowed}."
        )
    return model


def required_model_configs() -> list[dict[str, str]]:
    return [
        {"type": model.model_type, "name": model.model_name}
        for model in ALLOWED_MODELS.values()
    ]
