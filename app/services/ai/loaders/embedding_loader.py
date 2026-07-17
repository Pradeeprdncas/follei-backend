"""Embedding Loader (legacy shim) — delegates to LocalEmbeddingLoader.

This file is kept for backward compatibility only.
All new code should import directly from
app.services.ai.loaders.local_embedding_loader.

CLOUD API CALLS REMOVED: no httpx/Mistral calls remain.
"""
from loguru import logger
from app.services.ai.loaders.local_embedding_loader import LocalEmbeddingLoader


class EmbeddingLoader(LocalEmbeddingLoader):
    """Backward-compatible alias — wraps LocalEmbeddingLoader.

    Instantiating this class is identical to using LocalEmbeddingLoader.
    The old Mistral cloud path has been removed.
    """

    def __init__(self, model_name: str = "nomic-embed-text-v1.5"):
        logger.debug(
            "EmbeddingLoader is a shim for LocalEmbeddingLoader. "
            "Update your import to LocalEmbeddingLoader."
        )
        super().__init__(model_name=model_name)