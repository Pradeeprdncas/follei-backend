"""Model Registry - Centralized model management for local and cloud models.

This module provides:
- Model registration and discovery
- Lazy loading of models
- Model lifecycle management
- Fallback strategies
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class BaseModelLoader(ABC):
    """Abstract base class for all model loaders."""
    
    def __init__(self, model_name: str, model_path: Optional[Path] = None):
        self.model_name = model_name
        self.model_path = model_path
        self._model: Any = None
        self._loaded = False
    
    @abstractmethod
    async def load(self) -> None:
        """Load the model into memory."""
        pass
    
    @abstractmethod
    async def unload(self) -> None:
        """Unload the model from memory."""
        pass
    
    @abstractmethod
    async def infer(self, *args, **kwargs) -> Any:
        """Run inference on the model."""
        pass
    
    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self._loaded
    
    async def ensure_loaded(self) -> None:
        """Ensure model is loaded before inference."""
        if not self._loaded:
            await self.load()


class ModelRegistry:
    """Central registry for all AI models.
    
    Manages:
    - Model registration
    - Lazy loading
    - Model lifecycle
    - Fallback strategies
    """
    
    def __init__(self):
        self._models: Dict[str, BaseModelLoader] = {}
        self._fallback_enabled = True
        self._cloud_fallbacks: Dict[str, str] = {
            "embedding": "mistral-embed",
            "generator": "mistral-medium-2508",
            "verifier": "mistral-medium-2508",
            "summarizer": "mistral-medium-2508",
            "query_optimizer": "mistral-medium-2508",
            "classifier": "mistral-medium-2508",
            "reranker": "mistral-medium-2508",
        }
    
    def register(self, model_type: str, loader: BaseModelLoader) -> None:
        """Register a model loader.
        
        Args:
            model_type: Type of model (embedding, generator, etc.)
            loader: Model loader instance
        """
        self._models[model_type] = loader
        logger.info(f"Registered model loader: {model_type} -> {loader.model_name}")
    
    def get(self, model_type: str) -> Optional[BaseModelLoader]:
        """Get a model loader by type.
        
        Args:
            model_type: Type of model to retrieve
            
        Returns:
            Model loader instance or None if not found
        """
        return self._models.get(model_type)
    
    async def get_model(self, model_type: str) -> Optional[BaseModelLoader]:
        """Get a model, ensuring it's loaded.
        
        Args:
            model_type: Type of model to retrieve
            
        Returns:
            Loaded model loader or None
        """
        loader = self.get(model_type)
        if loader:
            await loader.ensure_loaded()
        return loader
    
    def get_fallback_model(self, model_type: str) -> Optional[str]:
        """Get fallback cloud model name for a given type.
        
        Args:
            model_type: Type of model
            
        Returns:
            Cloud model name or None
        """
        return self._cloud_fallbacks.get(model_type)
    
    def enable_fallback(self, enabled: bool = True) -> None:
        """Enable or disable cloud fallback.
        
        Args:
            enabled: Whether to enable fallback to cloud models
        """
        self._fallback_enabled = enabled
        logger.info(f"Cloud fallback {'enabled' if enabled else 'disabled'}")
    
    async def unload_all(self) -> None:
        """Unload all loaded models."""
        for loader in self._models.values():
            if loader.is_loaded:
                await loader.unload()
        logger.info("All models unloaded")
    
    def list_models(self) -> Dict[str, Dict[str, Any]]:
        """List all registered models and their status.
        
        Returns:
            Dictionary of model info
        """
        return {
            model_type: {
                "name": loader.model_name,
                "path": str(loader.model_path) if loader.model_path else None,
                "loaded": loader.is_loaded,
            }
            for model_type, loader in self._models.items()
        }


# Singleton registry instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get or create the singleton model registry.
    
    Returns:
        ModelRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
        logger.info("Model registry initialized")
    return _registry


# Convenience functions for common model types
async def get_embedding_model() -> Optional[BaseModelLoader]:
    """Get the embedding model."""
    return await get_model_registry().get_model("embedding")


async def get_generator_model() -> Optional[BaseModelLoader]:
    """Get the generator model."""
    return await get_model_registry().get_model("generator")


async def get_verifier_model() -> Optional[BaseModelLoader]:
    """Get the verifier model."""
    return await get_model_registry().get_model("verifier")


async def get_reranker_model() -> Optional[BaseModelLoader]:
    """Get the reranker model."""
    return await get_model_registry().get_model("reranker")


async def get_summarizer_model() -> Optional[BaseModelLoader]:
    """Get the summarizer model."""
    return await get_model_registry().get_model("summarizer")


async def get_query_optimizer_model() -> Optional[BaseModelLoader]:
    """Get the query optimizer model."""
    return await get_model_registry().get_model("query_optimizer")


async def get_classifier_model() -> Optional[BaseModelLoader]:
    """Get the classifier/intent model."""
    return await get_model_registry().get_model("classifier")