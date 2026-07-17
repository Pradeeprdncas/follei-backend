"""Base Loader - Abstract interface for all AI model loaders.

Every loader MUST inherit from this and implement all methods.
This ensures consistent APIs across cloud, local, and hybrid models.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger

from app.services.ai.runtime.results import (
    GenerationResult,
    EmbeddingResult,
    RerankResult,
    ClassificationResult,
    VerificationResult,
    PlanResult,
    QueryRewriteResult,
    SummaryResult,
)


class BaseLoader(ABC):
    """Abstract base class for all model loaders.
    
    Every loader must implement these methods with these exact signatures.
    No exceptions. No strings. No dicts. Only standardized result types.
    """
    
    def __init__(self, model_name: str, model_path: Optional[str] = None, **kwargs):
        """Initialize loader.
        
        Args:
            model_name: Human-readable model name (e.g., "qwen3b-base")
            model_path: Path to model files or model identifier
            **kwargs: Additional configuration (device, dtype, etc.)
        """
        self.model_name = model_name
        self.model_path = model_path or ""
        self.config = kwargs
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def _normalize_path(self, path) -> str:
        """Resolve and normalize path to string."""
        if isinstance(path, Path):
            return str(path.resolve())
        return str(Path(path).resolve())

    def _check_cuda(self) -> bool:
        """Check if CUDA (GPU) is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def ensure_loaded(self) -> None:
        """Ensure the model is loaded before inference."""
        if not self._loaded:
            await self.load()
    
    @abstractmethod
    async def load(self) -> None:
        """Load model into memory/GPU.
        
        Must set self._loaded = True on success.
        Must set self._model and self._tokenizer if applicable.
        """
        pass
    
    @abstractmethod
    async def unload(self) -> None:
        """Unload model from memory/GPU.
        
        Must set self._loaded = False.
        Must clean up self._model and self._tokenizer.
        """
        pass
    
    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self._loaded
    
    # ========== GENERATION ==========
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> GenerationResult:
        """Generate text from prompt.
        
        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic)
            top_p: Nucleus sampling parameter
            **kwargs: Additional generation parameters
            
        Returns:
            GenerationResult with text and metadata
        """
        pass
    
    # ========== EMBEDDING ==========
    
    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for text.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbeddingResult with vector and metadata
        """
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of EmbeddingResult objects
        """
        pass
    
    # ========== CLASSIFICATION ==========
    
    @abstractmethod
    async def classify(self, text: str) -> ClassificationResult:
        """Classify text into categories.
        
        Args:
            text: Input text to classify
            
        Returns:
            ClassificationResult with intent and confidence
        """
        pass
    
    # ========== RERANKING ==========
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
    ) -> RerankResult:
        """Rerank documents by relevance to query.
        
        Args:
            query: Query text
            documents: List of document texts
            top_k: Number of top results to return
            
        Returns:
            RerankResult with ranked documents and scores
        """
        pass
    
    # ========== VERIFICATION ==========
    
    @abstractmethod
    async def verify(
        self,
        question: str,
        answer: str,
        context: str,
    ) -> VerificationResult:
        """Verify if answer is correct given context.
        
        Args:
            question: Original question
            answer: Generated answer
            context: Retrieved context
            
        Returns:
            VerificationResult with correctness and confidence
        """
        pass
    
    # ========== PLANNING ==========
    
    @abstractmethod
    async def plan(self, goal: str, context: Optional[str] = None) -> PlanResult:
        """Create execution plan for goal.
        
        Args:
            goal: High-level goal to plan for
            context: Optional context information
            
        Returns:
            PlanResult with ordered steps
        """
        pass
    
    # ========== QUERY REWRITING ==========
    
    @abstractmethod
    async def rewrite_query(self, query: str) -> QueryRewriteResult:
        """Rewrite query for better retrieval.
        
        Args:
            query: Original user query
            
        Returns:
            QueryRewriteResult with optimized query
        """
        pass
    
    # ========== SUMMARIZATION ==========
    
    @abstractmethod
    async def summarize(
        self,
        text: str,
        max_length: Optional[int] = None,
    ) -> SummaryResult:
        """Summarize text.
        
        Args:
            text: Text to summarize
            max_length: Optional maximum summary length
            
        Returns:
            SummaryResult with condensed text
        """
        pass
    
    # ========== WARMUP ==========
    
    @abstractmethod
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input.
        
        Returns:
            Dict with warmup results (time, status)
        """
        pass
    
    # ========== HEALTH ==========
    
    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Check model health status.
        
        Returns:
            Dict with health status and details
        """
        pass
    
    # ========== UTILITY METHODS ==========
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "name": self.model_name,
            "path": self.model_path,
            "loaded": self._loaded,
            "type": self.__class__.__name__,
        }
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.model_name}, loaded={self._loaded})"


class BaseLocalLoader(BaseLoader):
    """Base loader class for all local models."""
    
    def __init__(self, model_name: str, model_path: Optional[str] = None, **kwargs):
        super().__init__(model_name=model_name, model_path=model_path, **kwargs)
        
    async def load(self) -> None:
        pass
        
    async def unload(self) -> None:
        pass
        
    def is_loaded(self) -> bool:
        return self._loaded
        
    async def generate(self, prompt: str, **kwargs) -> GenerationResult:
        raise NotImplementedError()
        
    async def embed(self, text: str) -> EmbeddingResult:
        raise NotImplementedError()
        
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        raise NotImplementedError()
        
    async def classify(self, text: str) -> ClassificationResult:
        raise NotImplementedError()
        
    async def rerank(self, query: str, documents: List[str], top_k: int = 5) -> RerankResult:
        raise NotImplementedError()
        
    async def verify(self, question: str, answer: str, context: str) -> VerificationResult:
        raise NotImplementedError()
        
    async def plan(self, goal: str, context: Optional[str] = None) -> PlanResult:
        raise NotImplementedError()
        
    async def rewrite_query(self, query: str) -> QueryRewriteResult:
        raise NotImplementedError()
        
    async def summarize(self, text: str, max_length: Optional[int] = None) -> SummaryResult:
        raise NotImplementedError()


class BaseCloudLoader(BaseLoader):
    """Base loader class for all cloud-based models (e.g. Mistral API)."""
    
    def __init__(self, model_name: str, api_key: str, api_base: str, **kwargs):
        super().__init__(model_name=model_name, model_path=api_base, **kwargs)
        self.api_key = api_key
        self.api_base = api_base

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    async def generate(self, prompt: str, **kwargs) -> GenerationResult:
        raise NotImplementedError()

    async def embed(self, text: str) -> EmbeddingResult:
        raise NotImplementedError()

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        raise NotImplementedError()

    async def classify(self, text: str) -> ClassificationResult:
        raise NotImplementedError()

    async def rerank(self, query: str, documents: List[str], top_k: int = 5) -> RerankResult:
        raise NotImplementedError()

    async def verify(self, question: str, answer: str, context: str) -> VerificationResult:
        raise NotImplementedError()

    async def plan(self, goal: str, context: Optional[str] = None) -> PlanResult:
        raise NotImplementedError()

    async def rewrite_query(self, query: str) -> QueryRewriteResult:
        raise NotImplementedError()

    async def summarize(self, text: str, max_length: Optional[int] = None) -> SummaryResult:
        raise NotImplementedError()