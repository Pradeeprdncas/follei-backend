"""AI Model Loaders - Concrete implementations for different model types.

This module provides:
- Embedding loaders (local and cloud)
- Generator loaders (local via llama.cpp GGUF)
- Verifier loaders
- Reranker loaders
- Summarizer loaders
- Query optimizer loaders
- Classifier loaders
"""
from app.services.ai.loaders.base_loader import BaseLocalLoader, BaseCloudLoader
from app.services.ai.loaders.local_embedding_loader import LocalEmbeddingLoader
from app.services.ai.loaders.local_gguf_model_loader import LocalGGUFModelLoader
from app.services.ai.loaders.local_classifier_loader import LocalClassifierLoader
from app.services.ai.loaders.local_summarizer_loader import LocalSummarizerLoader
from app.services.ai.loaders.local_query_loader import LocalQueryOptimizerLoader
from app.services.ai.loaders.local_reranker_loader import LocalRerankerLoader
from app.services.ai.loaders.local_verifier_loader import LocalVerifierLoader
from app.services.ai.loaders.local_planner_loader import LocalPlannerLoader

# LEGACY TRANSFORMERS: kept for reference, not used in production
# from app.services.ai.loaders.local_generator_loader import LocalGeneratorLoader

# Short-form aliases used by legacy code and tests
EmbeddingLoader = LocalEmbeddingLoader
GeneratorLoader = LocalGGUFModelLoader   # Replaced transformers AutoModelForCausalLM → llama.cpp GGUF
ClassifierLoader = LocalClassifierLoader
SummarizerLoader = LocalSummarizerLoader
QueryOptimizerLoader = LocalQueryOptimizerLoader
RerankerLoader = LocalRerankerLoader
VerifierLoader = LocalVerifierLoader
PlannerLoader = LocalPlannerLoader

__all__ = [
    # Base classes
    "BaseLocalLoader",
    "BaseCloudLoader",
    # Full-name locals
    "LocalEmbeddingLoader",
    "LocalGGUFModelLoader",
    "LocalClassifierLoader",
    "LocalSummarizerLoader",
    "LocalQueryOptimizerLoader",
    "LocalRerankerLoader",
    "LocalVerifierLoader",
    "LocalPlannerLoader",
    # Short aliases
    "EmbeddingLoader",
    "GeneratorLoader",
    "ClassifierLoader",
    "SummarizerLoader",
    "QueryOptimizerLoader",
    "RerankerLoader",
    "VerifierLoader",
    "PlannerLoader",
]
