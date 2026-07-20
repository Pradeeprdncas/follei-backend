"""Local Reranker Loader - BGE-reranker-base for document reranking.

Uses transformers AutoModelForSequenceClassification for local inference.
"""
from typing import Dict, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader

_settings = get_settings()


class LocalRerankerLoader(BaseLocalLoader):
    """Local reranker using BGE-reranker-base.
    
    Loads model from AI_MODELS/rerankers/bge-reranker-base
    """

    def __init__(self, model_name: str = "bge-reranker-base"):
        """Initialize local reranker loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "rerankers" / model_name

    async def load(self) -> None:
        """Load BGE-reranker-base model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local reranker model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info("Loading BGE-reranker-base model...")
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local reranker loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local reranker: {e}")
            raise

    async def unload(self) -> None:
        """Unload model."""
        if self._model:
            del self._model
            self._model = None
        if self._tokenizer:
            del self._tokenizer
            self._tokenizer = None
        self._loaded = False
        logger.info("Local reranker unloaded")

    async def rerank(
        self,
        query: str,
        documents: list,
        top_k: int = 5,
    ) -> list:
        """Rerank documents by relevance to query.

        Args:
            query: Search query
            documents: List of document strings
            top_k: Number of top documents to return

        Returns:
            List of (document, score) tuples, sorted by score descending
        """
        try:
            await self.ensure_loaded()
            import torch

            # Prepare pairs: [query, doc1], [query, doc2], ...
            pairs = [[query, doc] for doc in documents]

            # Tokenize
            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self._model.device)

            # Score
            with torch.no_grad():
                outputs = self._model(**inputs)
                scores = outputs.logits.squeeze(-1)

            # Convert to list and sort
            scored_docs = [
                (doc, float(score.item())) 
                for doc, score in zip(documents, scores)
            ]
            scored_docs.sort(key=lambda x: x[1], reverse=True)

            logger.debug(f"Reranked {len(documents)} documents, top score: {scored_docs[0][1]:.3f}")
            top_scored = scored_docs[:top_k]
            
            from app.services.ai.runtime.results import RerankResult
            return RerankResult(
                documents=[doc for doc, _ in top_scored],
                scores=[score for _, score in top_scored],
                query=query,
                model=self.model_name
            )

        except Exception as e:
            logger.error(f"Local reranking failed: {e}")
            from app.services.ai.runtime.results import RerankResult
            return RerankResult(
                documents=documents[:top_k],
                scores=[0.0] * len(documents[:top_k]),
                query=query,
                model=self.model_name
            )

    async def infer(self, query: str, documents: list, **kwargs) -> Any:
        """Alias for rerank."""
        return await self.rerank(query, documents, **kwargs)
    
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
            await self.rerank(
                query="test",
                documents=["doc1", "doc2"],
                top_k=2
            )
            
            elapsed = time.perf_counter() - start
            logger.debug(f"Reranker warmup: {elapsed:.3f}s")
            
            return {
                "status": "ok",
                "time_s": elapsed,
                "model": self.model_name,
            }
        except Exception as e:
            logger.error(f"Reranker warmup failed: {e}")
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
            await self.rerank(
                query="health check",
                documents=["test"],
                top_k=1
            )
            
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
