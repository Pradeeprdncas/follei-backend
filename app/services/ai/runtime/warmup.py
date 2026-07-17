"""Model Warmup - Runs dummy inference to warm up all loaded models.

Warms up each model type with tiny inputs so the first real request is fast.
"""
import asyncio
import time
from typing import Dict, Any
from loguru import logger


class ModelWarmup:
    """Warms up all loaded AI models with dummy inputs.

    Only responsibility: warmup
    Never downloads, never benchmarks.
    """

    def __init__(self):
        """Initialize warmup engine.
        
        NOTE: This is called automatically, but actual warmup should only
        happen when explicitly triggered by BootstrapManager.
        """
        self.warmup_times: Dict[str, float] = {}
        self.errors: list[str] = []
        self._bootstrap_initialized = False
    
    def initialize(self) -> None:
        """Explicit initialization called by BootstrapManager.
        
        This method MUST be called during startup before any warmup operations.
        """
        if self._bootstrap_initialized:
            logger.warning("ModelWarmup already initialized")
            return
        
        logger.info("ModelWarmup bootstrap initialization")
        self._bootstrap_initialized = True

    async def warmup_all(self) -> Dict[str, Any]:
        """Warm up every known model type.

        Returns:
            Warmup results with times and errors
        """
        start = time.perf_counter()
        logger.info("Starting model warmup...")

        # Warm up in sequence so we don't spike VRAM
        warmup_order = [
            ("embedding", self._warmup_embedding),
            ("query_optimizer", self._warmup_query),
            ("generator", self._warmup_generator),
            ("reranker", self._warmup_reranker),
        ]

        for key, func in warmup_order:
            try:
                t0 = time.perf_counter()
                await func()
                elapsed = time.perf_counter() - t0
                self.warmup_times[key] = elapsed
                logger.debug(f"  {key}: {elapsed:.3f}s")
            except Exception as e:
                logger.warning(f"  {key} warmup failed: {e}")
                self.errors.append(f"{key}: {e}")

        total = time.perf_counter() - start
        logger.info(f"Warmup complete: {len(self.warmup_times)} ok, {len(self.errors)} failed, {total:.2f}s total")
        return {
            "times": self.warmup_times,
            "errors": self.errors,
            "total_s": total,
        }

    async def _warmup_embedding(self) -> None:
        """Warm up embedding model with minimal forward pass.
        """
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        result = await manager.get_model("embedding", "nomic-embed-text-v1.5")
        model = result.get("model")
        
        if not model:
            logger.warning("Embedding warmup skipped: model not available")
            return
        
        try:
            if hasattr(model, "encode"):
                await asyncio.to_thread(model.encode, ["test"], show_progress_bar=False)
            logger.debug("Embedding warmup complete")
        except Exception as e:
            logger.debug(f"Embedding warmup skipped: {e}")

    async def _warmup_generator(self) -> None:
        """Warm up generator with a single forward pass (no generation).
        
        Skips torch.compile() and autoregressive generation — too expensive
        at startup on CPU. First real request will pay the one-time cost.
        """
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        result = await manager.get_model("generator", "qwen2.5-3b-instruct")
        tokenizer = result.get("tokenizer")
        model = result.get("model")
        
        if not (tokenizer and model):
            logger.warning("Generator warmup skipped: model or tokenizer not available")
            return
        
        try:
            import torch
            inputs = tokenizer("Hi", return_tensors="pt", truncation=True, max_length=8)
            if torch.cuda.is_available():
                inputs = inputs.to("cuda")
            with torch.no_grad():
                _ = model(**inputs)
            logger.debug("Generator warmup complete (forward pass only)")
        except Exception as e:
            logger.debug(f"Generator warmup skipped: {e}")

    async def _warmup_query(self) -> None:
        """Warm up query rewriter with a single forward pass (no generation).
        """
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        result = await manager.get_model("query_optimizer", "qwen2.5-0.5b")
        tokenizer = result.get("tokenizer")
        model = result.get("model")
        
        if not (tokenizer and model):
            logger.warning("Query optimizer warmup skipped: model or tokenizer not available")
            return
        
        try:
            import torch
            inputs = tokenizer("test", return_tensors="pt", truncation=True, max_length=8)
            if torch.cuda.is_available():
                inputs = inputs.to("cuda")
            with torch.no_grad():
                _ = model(**inputs)
            logger.debug("Query optimizer warmup complete (forward pass only)")
        except Exception as e:
            logger.debug(f"Query optimizer warmup skipped: {e}")

    async def _warmup_reranker(self) -> None:
        """Warm up reranker with a tiny pair."""
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        result = await manager.get_model("reranker", "bge-reranker-base")
        tokenizer = result.get("tokenizer")
        model = result.get("model")
        if tokenizer and model and hasattr(model, "compute_similarity"):
            await asyncio.to_thread(
                model.compute_similarity,
                ["query"],
                ["document"],
            )
        elif tokenizer and model:
            import torch
            inputs = tokenizer(
                ["query", "document"],
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=16,
            )
            with torch.no_grad():
                _ = model(**inputs)

    async def warmup_single(self, model_type: str, model_name: str) -> float:
        """Warm up a single model by type and name (forward pass only)."""
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        result = await manager.get_model(model_type, model_name)
        tokenizer = result.get("tokenizer")
        model = result.get("model")
        key = f"{model_type}:{model_name}"

        t0 = time.perf_counter()
        if tokenizer and model:
            import torch
            inputs = tokenizer("warmup", return_tensors="pt", truncation=True, max_length=8)
            if torch.cuda.is_available():
                inputs = inputs.to("cuda")
            with torch.no_grad():
                _ = model(**inputs)
        elapsed = time.perf_counter() - t0
        self.warmup_times[key] = elapsed
        logger.debug(f"Warmup {key}: {elapsed:.3f}s")
        return elapsed

    def get_warmup_times(self) -> Dict[str, float]:
        """Get completed warmup times.

        Returns:
            Mapping of model key to seconds
        """
        return dict(self.warmup_times)

    def clear(self) -> None:
        """Reset warmup state."""
        self.warmup_times.clear()
        self.errors.clear()


# Singleton
_warmup: ModelWarmup = None


def get_model_warmup() -> ModelWarmup:
    """Get or create warmup instance."""
    global _warmup
    if _warmup is None:
        _warmup = ModelWarmup()
    return _warmup
