"""Model Manager - Centralized model lifecycle management.

Singleton that owns ALL models:
- Lazy loading
- Caching and reuse
- Reference counting
- Memory tracking
- Thread-safe access
- Proper unloading
- LRU eviction
"""
import asyncio
import time
import psutil
import torch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.model_policy import require_allowed_model

_settings = get_settings()


@dataclass
class ModelInfo:
    """Complete model metadata and tracking."""
    model_key: str
    model_type: str
    model_name: str
    loader: Any  # ModelLoader instance
    
    # Model components (shared, not duplicated)
    model: Any = None
    tokenizer: Any = None
    processor: Any = None
    config: Any = None
    
    # Tracking
    ref_count: int = 0  # How many active users
    load_time: float = 0.0  # Seconds to load
    load_timestamp: float = 0.0  # When loaded
    last_used: float = 0.0  # Last access time
    memory_bytes: int = 0  # Estimated memory usage
    device: str = "cpu"  # "cpu", "cuda", "mps"
    
    # Status
    is_loaded: bool = False
    load_error: Optional[str] = None
    
    def update_last_used(self) -> None:
        """Update last used timestamp."""
        self.last_used = time.time()
    
    def increment_ref(self) -> None:
        """Increment reference count."""
        self.ref_count += 1
        self.update_last_used()
    
    def decrement_ref(self) -> int:
        """Decrement reference count.
        
        Returns:
            New reference count
        """
        self.ref_count = max(0, self.ref_count - 1)
        return self.ref_count
    
    def get_age_seconds(self) -> float:
        """Get time since model was loaded."""
        if self.load_timestamp == 0:
            return 0
        return time.time() - self.load_timestamp
    
    def get_idle_seconds(self) -> float:
        """Get time since last use."""
        if self.last_used == 0:
            return self.get_age_seconds()
        return time.time() - self.last_used


class ModelManager:
    """Centralized model manager - sole owner of all AI models.
    
    Responsibilities:
    - Own all model instances (no loader owns models)
    - Lazy load on first request
    - Cache and reuse models
    - Reference counting
    - Memory tracking
    - Thread-safe access
    - LRU eviction
    - Proper unloading
    
    No model is instantiated outside this class.
    """
    
    _instance = None
    _instance_lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize model manager.
        
        NOTE: Actual initialization must be done via initialize() by BootstrapManager.
        """
        if self._initialized:
            return
        
        # Model storage: model_key -> ModelInfo
        self._models: Dict[str, ModelInfo] = {}
        
        # Locks for thread-safe operations
        self._global_lock = asyncio.Lock()
        self._model_locks: Dict[str, asyncio.Lock] = {}
        
        # Configuration
        self._max_models_in_memory = 10  # LRU eviction threshold
        self._idle_timeout_seconds = 3600  # 1 hour idle before eviction
        
        # Bootstrap flag
        self._bootstrap_initialized = False
        self._initialized = True
    
    def initialize(self) -> None:
        """Explicit initialization called by BootstrapManager.
        
        MUST be called before any model operations.
        """
        if self._bootstrap_initialized:
            logger.warning("ModelManager already initialized")
            return
        
        logger.info("ModelManager bootstrap initialization")
        self._bootstrap_initialized = True
    
    async def get_model(self, model_type: str, model_name: str) -> Dict[str, Any]:
        """Get a model, loading it if necessary.
        
        This is the ONLY way to access models.
        All loaders return components to ModelManager, not to callers.
        
        Args:
            model_type: Type of model (generator, embedding, etc.)
            model_name: Name of the model
            
        Returns:
            Dict with model, tokenizer, processor, config, and metadata
        """
        require_allowed_model(model_type, model_name)
        model_key = f"{model_type}:{model_name}"
        
        # Get or create lock for this model
        if model_key not in self._model_locks:
            async with self._global_lock:
                if model_key not in self._model_locks:
                    self._model_locks[model_key] = asyncio.Lock()
        
        # Thread-safe model access
        async with self._model_locks[model_key]:
            # Check if already loaded
            if model_key in self._models:
                model_info = self._models[model_key]
                if model_info.is_loaded:
                    logger.debug(f"Model {model_key} already loaded (ref_count={model_info.ref_count})")
                    model_info.increment_ref()
                    return self._model_info_to_dict(model_info)
            
            # Load the model
            return await self._load_model(model_type, model_name)
    
    async def release_model(self, model_type: str, model_name: str) -> None:
        """Release a model reference (decrement ref count).
        
        Args:
            model_type: Type of model
            model_name: Name of the model
        """
        model_key = f"{model_type}:{model_name}"
        
        if model_key not in self._models:
            return
        
        model_info = self._models[model_key]
        new_count = model_info.decrement_ref()
        
        logger.debug(f"Released {model_key} (ref_count={new_count})")
        
        # Unload if no more references
        if new_count == 0:
            await self._maybe_unload_model(model_key)
    
    async def _load_model(self, model_type: str, model_name: str) -> Dict[str, Any]:
        """Load a model and take ownership.
        
        Args:
            model_type: Type of model
            model_name: Name of the model
            
        Returns:
            Dict with model components
        """
        model_key = f"{model_type}:{model_name}"
        
        try:
            logger.info(f"Loading model: {model_key}")
            load_start = time.perf_counter()
            
            # Get the appropriate loader
            loader = self._get_loader(model_type, model_name)
            
            # Load the model (loader returns components, we own them)
            load_result = await loader.load()
            
            # Extract components from loader
            # Loader should return dict with model, tokenizer, processor, config
            if isinstance(load_result, dict):
                model = load_result.get("model")
                tokenizer = load_result.get("tokenizer")
                processor = load_result.get("processor")
                config = load_result.get("config")
            else:
                # Fallback: get from loader attributes
                model = getattr(loader, '_model', None)
                tokenizer = getattr(loader, '_tokenizer', None)
                processor = getattr(loader, '_processor', None)
                config = getattr(loader, '_config', None)
            
            # Estimate memory usage
            memory_bytes = self._estimate_memory(model, tokenizer)
            
            # Detect device
            device = "cpu"
            if model is not None and hasattr(model, 'device'):
                device = str(model.device)
            elif torch.cuda.is_available():
                device = "cuda"
            
            # Create model info
            load_time = time.perf_counter() - load_start
            model_info = ModelInfo(
                model_key=model_key,
                model_type=model_type,
                model_name=model_name,
                loader=loader,
                model=model,
                tokenizer=tokenizer,
                processor=processor,
                config=config,
                ref_count=1,  # Initial reference
                load_time=load_time,
                load_timestamp=time.time(),
                last_used=time.time(),
                memory_bytes=memory_bytes,
                device=device,
                is_loaded=True,
            )
            
            # Store in cache
            async with self._global_lock:
                self._models[model_key] = model_info
                self._check_eviction()
            
            logger.info(
                f"Model loaded: {model_key} "
                f"(load_time={load_time:.2f}s, memory={memory_bytes / 1024**2:.0f}MB, device={device})"
            )
            
            return self._model_info_to_dict(model_info)
            
        except Exception as e:
            logger.error(f"Failed to load model {model_key}: {e}")
            raise
    
    async def _maybe_unload_model(self, model_key: str) -> None:
        """Unload model if no references and conditions met.
        
        Args:
            model_key: Model key to potentially unload
        """
        if model_key not in self._models:
            return
        
        model_info = self._models[model_key]
        
        # Only unload if no references
        if model_info.ref_count > 0:
            return
        
        # Check if idle for too long
        idle_seconds = model_info.get_idle_seconds()
        if idle_seconds < self._idle_timeout_seconds:
            return
        
        # Unload
        await self._unload_model(model_key)
    
    async def _unload_model(self, model_key: str) -> None:
        """Force unload a model.
        
        Args:
            model_key: Model key to unload
        """
        if model_key not in self._models:
            return
        
        model_info = self._models[model_key]
        
        try:
            logger.info(f"Unloading model: {model_key}")
            
            # Call loader unload
            if hasattr(model_info.loader, 'unload'):
                await model_info.loader.unload()
            
            # Clear references
            model_info.model = None
            model_info.tokenizer = None
            model_info.processor = None
            model_info.config = None
            model_info.is_loaded = False
            
            # Remove from cache
            async with self._global_lock:
                del self._models[model_key]
            
            # Clear GPU cache
            self._clear_gpu_cache()
            
            logger.info(f"Model unloaded: {model_key}")
            
        except Exception as e:
            logger.error(f"Failed to unload model {model_key}: {e}")
    
    async def unload_model(self, model_type: str, model_name: str) -> None:
        """Public API to unload a specific model.
        
        Args:
            model_type: Type of model
            model_name: Name of the model
        """
        model_key = f"{model_type}:{model_name}"
        await self._unload_model(model_key)
    
    async def unload_all(self) -> None:
        """Unload all models."""
        logger.info("Unloading all models...")
        
        async with self._global_lock:
            model_keys = list(self._models.keys())
        
        for model_key in model_keys:
            try:
                await self._unload_model(model_key)
            except Exception as e:
                logger.error(f"Failed to unload {model_key}: {e}")
        
        logger.info("All models unloaded")
    
    def _check_eviction(self) -> None:
        """Check if LRU eviction is needed (must be called with global_lock held)."""
        if len(self._models) <= self._max_models_in_memory:
            return
        
        # Find oldest idle models
        idle_models = []
        for model_key, model_info in self._models.items():
            if model_info.ref_count == 0:
                idle_seconds = model_info.get_idle_seconds()
                idle_models.append((idle_seconds, model_key, model_info))
        
        # Sort by idle time (most idle first)
        idle_models.sort(key=lambda x: x[0], reverse=True)
        
        # Evict oldest idle models
        to_evict = len(self._models) - self._max_models_in_memory
        for i in range(min(to_evict, len(idle_models))):
            _, model_key, model_info = idle_models[i]
            logger.info(f"LRU eviction: {model_key} (idle={model_info.get_idle_seconds():.0f}s)")
            # Schedule unload (don't block)
            asyncio.create_task(self._unload_model(model_key))
    
    def _get_loader(self, model_type: str, model_name: str):
        require_allowed_model(model_type, model_name)
        if model_type in ("generator", "query_optimizer"):
            from app.services.ai.loaders.local_gguf_model_loader import LocalGGUFModelLoader
            return LocalGGUFModelLoader(model_name)
        elif model_type == "embedding":
            from app.services.ai.loaders.local_embedding_loader import LocalEmbeddingLoader
            return LocalEmbeddingLoader(model_name)
        elif model_type == "reranker":
            from app.services.ai.loaders.local_reranker_loader import LocalRerankerLoader
            return LocalRerankerLoader(model_name)
        elif model_type == "classifier":
            from app.services.ai.loaders.local_classifier_loader import LocalClassifierLoader
            return LocalClassifierLoader(model_name)
        elif model_type == "summarizer":
            from app.services.ai.loaders.local_summarizer_loader import LocalSummarizerLoader
            return LocalSummarizerLoader(model_name)
        elif model_type == "verifier":
            from app.services.ai.loaders.local_verifier_loader import LocalVerifierLoader
            return LocalVerifierLoader(model_name)
        elif model_type == "planner":
            from app.services.ai.loaders.local_planner_loader import LocalPlannerLoader
            return LocalPlannerLoader(model_name)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
    
    def _estimate_memory(self, model: Any, tokenizer: Any) -> int:
        """Estimate memory usage of model in bytes.
        
        Args:
            model: Model instance
            tokenizer: Tokenizer instance
            
        Returns:
            Estimated memory in bytes
        """
        try:
            total_bytes = 0
            
            # Model parameters
            if model is not None and hasattr(model, 'parameters'):
                for param in model.parameters():
                    total_bytes += param.numel() * param.element_size()
            
            # Tokenizer (rough estimate)
            if tokenizer is not None:
                total_bytes += 1024 * 1024  # 1MB estimate
            
            return total_bytes
        except Exception:
            return 0
    
    def _clear_gpu_cache(self) -> None:
        """Clear GPU cache if available."""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU cache cleared")
        except ImportError:
            pass
    
    def _model_info_to_dict(self, model_info: ModelInfo) -> Dict[str, Any]:
        """Convert ModelInfo to dict for backward compatibility.
        
        Args:
            model_info: ModelInfo instance
            
        Returns:
            Dict with model components
        """
        return {
            "loader": model_info.loader,
            "model": model_info.model,
            "tokenizer": model_info.tokenizer,
            "processor": model_info.processor,
            "config": model_info.config,
            "type": model_info.model_type,
            "name": model_info.model_name,
            "device": model_info.device,
            "ref_count": model_info.ref_count,
        }
    
    def get_model_info(self, model_type: str, model_name: str) -> Optional[ModelInfo]:
        """Get ModelInfo for a model.
        
        Args:
            model_type: Type of model
            model_name: Name of model
            
        Returns:
            ModelInfo or None if not loaded
        """
        model_key = f"{model_type}:{model_name}"
        return self._models.get(model_key)

    def get_loader_unsafe(self, model_type: str, model_name: str):
        """Fast-path: get loader without locks (caller must check is_loaded).
        
        Skips lock acquisition, ref-counting, and dict-building.
        Only safe for read-only access on already-loaded models.
        """
        model_key = f"{model_type}:{model_name}"
        info = self._models.get(model_key)
        if info and info.is_loaded and info.loader:
            return info.loader
        return None
    
    def get_all_model_info(self) -> Dict[str, ModelInfo]:
        """Get all loaded model info.
        
        Returns:
            Dict of model_key -> ModelInfo
        """
        return dict(self._models)
    
    def get_loaded_models(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all loaded models.
        
        Returns:
            Dictionary of model information
        """
        return {
            model_key: {
                "type": info.model_type,
                "name": info.model_name,
                "loaded": info.is_loaded,
                "ref_count": info.ref_count,
                "device": info.device,
                "memory_mb": info.memory_bytes / 1024**2,
                "load_time_s": info.load_time,
                "last_used_s": time.time() - info.last_used if info.last_used > 0 else 0,
            }
            for model_key, info in self._models.items()
        }
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get total memory usage.
        
        Returns:
            Memory usage statistics
        """
        total_bytes = sum(info.memory_bytes for info in self._models.values())
        return {
            "total_models": len(self._models),
            "total_memory_bytes": total_bytes,
            "total_memory_mb": total_bytes / 1024**2,
            "total_memory_gb": total_bytes / 1024**3,
            "models": {
                key: {
                    "memory_mb": info.memory_bytes / 1024**2,
                    "device": info.device,
                }
                for key, info in self._models.items()
            },
        }
    
    def is_model_loaded(self, model_type: str, model_name: str) -> bool:
        """Check if a model is loaded.
        
        Args:
            model_type: Type of model
            model_name: Name of model
            
        Returns:
            True if model is loaded
        """
        model_key = f"{model_type}:{model_name}"
        return model_key in self._models and self._models[model_key].is_loaded
    
    async def preload_models(self, model_configs: list[dict]) -> None:
        """Preload multiple models.
        
        Args:
            model_configs: List of dicts with 'type' and 'name' keys
        """
        logger.info(f"Preloading {len(model_configs)} models...")
        tasks = []
        for config in model_configs:
            model_type = config.get("type")
            model_name = config.get("name")
            if model_type and model_name:
                tasks.append(self.get_model(model_type, model_name))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Model preloading complete")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive model manager statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_models": len(self._models),
            "loaded_models": sum(1 for m in self._models.values() if m.is_loaded),
            "total_refs": sum(m.ref_count for m in self._models.values()),
            "memory": self.get_memory_usage(),
            "models": {
                key: {
                    "type": info.model_type,
                    "name": info.model_name,
                    "loaded": info.is_loaded,
                    "ref_count": info.ref_count,
                    "device": info.device,
                    "load_time_s": info.load_time,
                    "idle_s": info.get_idle_seconds(),
                    "memory_mb": info.memory_bytes / 1024**2,
                }
                for key, info in self._models.items()
            },
        }


# Singleton instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get or create the singleton ModelManager.
    
    Returns:
        ModelManager instance
    """
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


def _get_loaded_model_unsafe(model_type: str, model_name: str):
    """Fast-path: get loader for an already-loaded model, no locks.
    
    Returns None if model is not loaded yet (caller must fall back to get_model).
    """
    global _model_manager
    if _model_manager is not None:
        return _model_manager.get_loader_unsafe(model_type, model_name)
    return None
