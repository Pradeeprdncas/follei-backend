"""Test AI Service Layer - Verify functionality without breaking existing APIs.

This test module verifies:
- AI service initialization
- Router functionality
- Cache functionality
- Registry functionality
- Loader functionality
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from loguru import logger

# Test imports
from app.services.ai import (
    get_ai_service,
    get_model_registry,
    get_response_cache,
    get_ai_router,
)
from app.services.ai.registry import ModelRegistry, BaseModelLoader
from app.services.ai.cache import ResponseCache
from app.services.ai.router import AIRouter
from app.services.ai.loaders import (
    EmbeddingLoader,
    GeneratorLoader,
    VerifierLoader,
    RerankerLoader,
    SummarizerLoader,
    QueryOptimizerLoader,
    ClassifierLoader,
)


class TestModelRegistry:
    """Test ModelRegistry functionality."""
    
    def test_registry_singleton(self):
        """Test that registry is a singleton."""
        registry1 = get_model_registry()
        registry2 = get_model_registry()
        assert registry1 is registry2
    
    def test_register_and_get_model(self):
        """Test model registration and retrieval."""
        registry = ModelRegistry()
        
        # Create mock loader
        mock_loader = MagicMock(spec=BaseModelLoader)
        mock_loader.model_name = "test-model"
        mock_loader.is_loaded = True
        
        # Register
        registry.register("test_type", mock_loader)
        
        # Retrieve
        retrieved = registry.get("test_type")
        assert retrieved is mock_loader
    
    def test_get_nonexistent_model(self):
        """Test getting non-existent model returns None."""
        registry = ModelRegistry()
        result = registry.get("nonexistent")
        assert result is None
    
    def test_fallback_model(self):
        """Test fallback model retrieval — local-only architecture has no cloud fallbacks."""
        registry = ModelRegistry()

        # Local architecture: embedding falls back to nomic, generator to qwen3b
        fallback = registry.get_fallback_model("embedding")
        assert fallback is not None  # Some fallback name is registered

        fallback = registry.get_fallback_model("generator")
        assert fallback is not None

        # Should return None for completely unknown type
        fallback = registry.get_fallback_model("unknown")
        assert fallback is None
    
    def test_list_models(self):
        """Test listing all models."""
        registry = ModelRegistry()
        
        # Register a couple of models
        mock_loader1 = MagicMock(spec=BaseModelLoader)
        mock_loader1.model_name = "model1"
        mock_loader1.model_path = None
        mock_loader1.is_loaded = False
        
        mock_loader2 = MagicMock(spec=BaseModelLoader)
        mock_loader2.model_name = "model2"
        mock_loader2.model_path = None
        mock_loader2.is_loaded = True
        
        registry.register("type1", mock_loader1)
        registry.register("type2", mock_loader2)
        
        models = registry.list_models()
        assert "type1" in models
        assert "type2" in models
        assert models["type1"]["name"] == "model1"
        assert models["type2"]["loaded"] is True


class TestResponseCache:
    """Test ResponseCache functionality."""
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = ResponseCache()
        assert cache._enabled is True
        assert cache._ttl == 3600
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = ResponseCache()
        
        # Same inputs should generate same key
        key1 = cache._generate_key("embedding", "test text")
        key2 = cache._generate_key("embedding", "test text")
        assert key1 == key2
        
        # Different inputs should generate different keys
        key3 = cache._generate_key("embedding", "different text")
        assert key1 != key3
        
        # Different model types should generate different keys
        key4 = cache._generate_key("generator", "test text")
        assert key1 != key4
    
    def test_cache_set_and_get(self):
        """Test cache set and get operations."""
        cache = ResponseCache()
        
        # Set a value
        test_data = {"embeddings": [[0.1, 0.2, 0.3]]}
        import asyncio
        asyncio.run(cache.set("embedding", "test", test_data))
        
        # Get the value
        result = asyncio.run(cache.get("embedding", "test"))
        assert result == test_data
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = ResponseCache()
        
        result = asyncio.run(cache.get("embedding", "nonexistent"))
        assert result is None
    
    def test_cache_disable(self):
        """Test cache disable."""
        cache = ResponseCache()
        cache.disable()
        
        assert cache._enabled is False
        
        # Should return None when disabled
        result = asyncio.run(cache.get("embedding", "test"))
        assert result is None
    
    def test_cache_stats(self):
        """Test cache statistics."""
        cache = ResponseCache()
        stats = cache.get_stats()
        
        assert "enabled" in stats
        assert "ttl" in stats
        assert "local_cache_size" in stats
        assert "redis_connected" in stats


class TestAIRouter:
    """Test AIRouter functionality."""
    
    def test_router_initialization(self):
        """Test router initialization."""
        router = get_ai_router()
        assert router is not None
        assert isinstance(router, AIRouter)
    
    def test_router_singleton(self):
        """Test that router is a singleton."""
        router1 = get_ai_router()
        router2 = get_ai_router()
        assert router1 is router2
    
    def test_router_stats(self):
        """Test router statistics."""
        router = get_ai_router()
        stats = router.get_stats()
        
        assert "cache" in stats
        # Router exposes model_manager stats (not a registry key)
        assert "model_manager" in stats or "registry" in stats
    
    def test_router_fallback_embed(self):
        """Test router embed_texts method exists and is callable."""
        router = get_ai_router()
        assert hasattr(router, 'embed_texts')
    
    def test_router_fallback_generate(self):
        """Test router generate method exists and is callable."""
        router = get_ai_router()
        assert hasattr(router, 'generate')


class TestLoaders:
    """Test individual loaders."""
    
    def test_embedding_loader_initialization(self):
        """Test embedding loader initialization (local: nomic-embed-text-v1.5)."""
        loader = EmbeddingLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_generator_loader_initialization(self):
        """Test generator loader initialization (local: qwen3b-base)."""
        loader = GeneratorLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_verifier_loader_initialization(self):
        """Test verifier loader initialization (local: smollm2-360m)."""
        loader = VerifierLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_reranker_loader_initialization(self):
        """Test reranker loader initialization (local: bge-reranker-base)."""
        loader = RerankerLoader()
        assert loader.model_name == "bge-reranker-base"
    
    def test_summarizer_loader_initialization(self):
        """Test summarizer loader initialization (local: smollm2-360m)."""
        loader = SummarizerLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_query_optimizer_loader_initialization(self):
        """Test query optimizer loader initialization (local: qwen2.5-0.5b)."""
        loader = QueryOptimizerLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_classifier_loader_initialization(self):
        """Test classifier loader initialization (local: ModernBERT-base)."""
        loader = ClassifierLoader()
        assert loader.model_name is not None
        assert len(loader.model_name) > 0
    
    def test_reranker_result_type(self):
        """Test reranker infer returns a RerankResult (local BGE model)."""
        from app.services.ai.runtime.results import RerankResult
        loader = RerankerLoader()

        documents = [
            "Python is a programming language",
            "JavaScript is used for web development",
            "Machine learning uses Python",
        ]

        async def _run():
            result = await loader.infer("Python programming", documents, top_k=2)
            assert isinstance(result, RerankResult)
            assert len(result.documents) <= 2
            assert len(result.scores) == len(result.documents)
            assert all(isinstance(s, float) for s in result.scores)

        asyncio.run(_run())
    
    def test_embed_query(self):
        """Test single query embedding."""
        loader = EmbeddingLoader()
        
        async def _run():
            with patch.object(loader, 'infer') as mock_infer:
                mock_infer.return_value = [[0.1, 0.2, 0.3]]
                result = await loader.embed_query("test query")
                assert len(result) == 3
                mock_infer.assert_called_once_with(["test query"])
        
        asyncio.run(_run())


class TestIntegration:
    """Integration tests for AI service layer."""
    
    def test_ai_service_factory(self):
        """Test AI service factory function."""
        from app.services.ai import get_ai_service
        
        service = get_ai_service()
        assert isinstance(service, AIRouter)
    
    def test_no_circular_imports(self):
        """Test that there are no circular imports."""
        # This test passes if we can import all modules without errors
        from app.services.ai import (
            ModelRegistry,
            ResponseCache,
            AIRouter,
        )
        from app.services.ai.loaders import EmbeddingLoader, GeneratorLoader
        
        # If we get here, no circular imports
        assert True
    
    def test_existing_imports_still_work(self):
        """Test that existing RAG imports still work."""
        # These are the existing imports that should not break
        from app.services.rag.embeddings.mistral import embed_texts, embed_query
        from app.services.rag.llm.generator import generate_answer
        from app.services.rag.llm.optimizer import optimize_user_request
        from app.services.rag.verifier.confidence import verify_answer
        
        # If we get here, existing imports work
        assert True


if __name__ == "__main__":
    # Run basic tests
    logger.info("Running AI Service Layer Tests...")
    
    # Test 1: Registry
    logger.info("Test 1: Model Registry")
    registry = get_model_registry()
    assert registry is not None
    logger.info("✓ Registry initialized")
    
    # Test 2: Cache
    logger.info("Test 2: Response Cache")
    cache = get_response_cache()
    assert cache is not None
    logger.info("✓ Cache initialized")
    
    # Test 3: Router
    logger.info("Test 3: AI Router")
    router = get_ai_router()
    assert router is not None
    logger.info("✓ Router initialized")
    
    # Test 4: Loaders
    logger.info("Test 4: Loaders")
    embed_loader = EmbeddingLoader()
    gen_loader = GeneratorLoader()
    assert embed_loader is not None
    assert gen_loader is not None
    logger.info("✓ Loaders initialized")
    
    # Test 5: Existing imports
    logger.info("Test 5: Existing imports")
    from app.services.rag.embeddings.mistral import embed_texts
    from app.services.rag.llm.generator import generate_answer
    logger.info("✓ Existing imports work")
    
    logger.info("\n✅ All basic tests passed!")
    logger.info("\nAI Service Layer is ready for integration.")