"""Local Embedding Loader - Nomic-embed-text-v1.5 for embeddings.

Uses sentence-transformers for local inference.
"""
from typing import List, Dict, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader
from app.services.ai.runtime.results import EmbeddingResult

_settings = get_settings()


class LocalEmbeddingLoader(BaseLocalLoader):
    """Local embedding loader using Nomic-embed-text-v1.5.
    
    Loads model from AI_MODELS/embeddings/nomic-embed-text-v1.5
    """
    
    def __init__(self, model_name: str = "nomic-embed-text-v1.5"):
        """Initialize local embedding loader.
        
        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._model_path = Path(_settings.AI_MODELS) / "embeddings" / model_name
    
    async def load(self) -> None:
        """Load embedding model."""
        if self._loaded:
            return
        
        try:
            logger.info(f"Loading local embedding model: {self.model_name}")
            
            from sentence_transformers import SentenceTransformer
            
            model_path = self._normalize_path(self._model_path)
            self._model = SentenceTransformer(
                model_path,
                device="cuda" if self._check_cuda() else "cpu",
                trust_remote_code=True,
            )
            
            self._loaded = True
            logger.info(f"Local embedding model loaded successfully: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            raise
    
    async def unload(self) -> None:
        """Unload model."""
        if self._model:
            del self._model
            self._model = None
        self._loaded = False
        logger.info("Local embedding model unloaded")
    
    async def infer(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts with explicit batching."""
        await self.ensure_loaded()
        
        try:
            n = len(texts)
            logger.info(f"Generating embeddings for {n} texts locally")
            
            import time
            t0 = time.perf_counter()
            
            embeddings = self._model.encode(
                texts,
                batch_size=32,
                convert_to_numpy=True,
                show_progress_bar=n > 10,
            )
            
            t1 = time.perf_counter()
            elapsed = t1 - t0
            per_item = elapsed / max(n, 1)
            logger.info(
                f"Embedded {n} texts in {elapsed:.3f}s ({per_item*1000:.1f}ms/item, "
                f"{n/elapsed:.1f} items/s)"
            )
            
            result = embeddings.tolist()
            return result
            
        except Exception as e:
            logger.error(f"Local embedding generation failed: {e}")
            raise
    
    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        from app.services.ai.runtime.results import EmbeddingResult
        embeddings = await self.infer([text])
        embedding = embeddings[0] if embeddings else []
        return EmbeddingResult(
            embedding=embedding,
            model=self.model_name
        )

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts."""
        from app.services.ai.runtime.results import EmbeddingResult
        embeddings = await self.infer(texts)
        return [
            EmbeddingResult(
                embedding=emb,
                model=self.model_name
            )
            for emb in embeddings
        ]

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector
        """
        embeddings = await self.infer([text])
        return embeddings[0] if embeddings else []
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input.
        
        Returns:
            Dict with warmup results
        """
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        
        try:
            import time
            start = time.perf_counter()
            
            # Tiny warmup inference
            await self.infer(["test"])
            
            elapsed = time.perf_counter() - start
            logger.debug(f"Embedding warmup: {elapsed:.3f}s")
            
            return {
                "status": "ok",
                "time_s": elapsed,
                "model": self.model_name,
            }
        except Exception as e:
            logger.error(f"Embedding warmup failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health.
        
        Returns:
            Dict with health status
        """
        if not self._loaded:
            return {
                "status": "not_loaded",
                "model": self.model_name,
                "loaded": False,
            }
        
        try:
            # Verify model is responsive
            await self.infer(["health check"])
            
            return {
                "status": "healthy",
                "model": self.model_name,
                "loaded": True,
                "device": "cuda" if self._check_cuda() else "cpu",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model_name,
                "loaded": True,
                "error": str(e),
            }
    
    def _check_cuda(self) -> bool:
        """Check if CUDA is available.
        
        Returns:
            True if CUDA is available
        """
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False