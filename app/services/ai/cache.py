"""Response Cache - Caching layer for AI model responses.

This module provides:
- Redis-based caching for model responses
- Semantic caching for similar queries
- TTL-based expiration
- Cache key generation
"""
from typing import Any, Dict, List, Optional
from hashlib import sha256
import json
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class ResponseCache:
    """Cache for AI model responses.
    
    Uses Redis for distributed caching with TTL expiration.
    Supports semantic caching for similar queries.
    """
    
    def __init__(self, redis_client=None):
        """Initialize cache.
        
        Args:
            redis_client: Optional Redis client instance
        """
        self._redis = redis_client
        self._local_cache: Dict[str, tuple] = {}  # Fallback local cache
        self._ttl = _settings.AI_CACHE_TTL if hasattr(_settings, 'AI_CACHE_TTL') else 3600
        self._enabled = True
    
    def _generate_key(self, model_type: str, inputs: Any) -> str:
        """Generate cache key from model type and inputs.
        
        Args:
            model_type: Type of model (embedding, generator, etc.)
            inputs: Model inputs (text, query, etc.)
            
        Returns:
            Cache key string
        """
        # Normalize inputs
        if isinstance(inputs, str):
            content = inputs
        elif isinstance(inputs, list):
            content = json.dumps(inputs, sort_keys=True)
        elif isinstance(inputs, dict):
            content = json.dumps(inputs, sort_keys=True)
        else:
            content = str(inputs)
        
        # Create hash
        key_data = f"{model_type}:{content}"
        key_hash = sha256(key_data.encode()).hexdigest()[:16]
        return f"ai_cache:{model_type}:{key_hash}"
    
    async def get(self, model_type: str, inputs: Any) -> Optional[Any]:
        """Get cached response.
        
        Args:
            model_type: Type of model
            inputs: Model inputs
            
        Returns:
            Cached response or None
        """
        if not self._enabled:
            return None
        
        key = self._generate_key(model_type, inputs)
        
        # Try Redis first
        if self._redis:
            try:
                cached = await self._redis.get(key)
                if cached:
                    logger.debug(f"Cache hit: {key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache get failed: {e}")
        
        # Fallback to local cache
        if key in self._local_cache:
            value, timestamp = self._local_cache[key]
            logger.debug(f"Local cache hit: {key}")
            return value
        
        return None
    
    async def set(self, model_type: str, inputs: Any, response: Any) -> None:
        """Cache a response.
        
        Args:
            model_type: Type of model
            inputs: Model inputs
            response: Model response to cache
        """
        if not self._enabled:
            return
        
        key = self._generate_key(model_type, inputs)
        
        # Try Redis first
        if self._redis:
            try:
                await self._redis.setex(
                    key,
                    self._ttl,
                    json.dumps(response)
                )
                logger.debug(f"Cache set: {key}")
                return
            except Exception as e:
                logger.warning(f"Redis cache set failed: {e}")
        
        # Fallback to local cache
        self._local_cache[key] = (response, None)
        logger.debug(f"Local cache set: {key}")
    
    async def invalidate(self, model_type: str, inputs: Any) -> None:
        """Invalidate a cached response.
        
        Args:
            model_type: Type of model
            inputs: Model inputs
        """
        key = self._generate_key(model_type, inputs)
        
        # Try Redis
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis cache invalidate failed: {e}")
        
        # Local cache
        self._local_cache.pop(key, None)
    
    async def clear(self, model_type: Optional[str] = None) -> None:
        """Clear cache.
        
        Args:
            model_type: Optional model type to clear (clears all if None)
        """
        if model_type:
            # Clear specific model type
            prefix = f"ai_cache:{model_type}:"
            if self._redis:
                try:
                    keys = await self._redis.keys(f"{prefix}*")
                    if keys:
                        await self._redis.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis cache clear failed: {e}")
            
            # Clear local cache
            self._local_cache = {
                k: v for k, v in self._local_cache.items()
                if not k.startswith(prefix)
            }
        else:
            # Clear all
            if self._redis:
                try:
                    keys = await self._redis.keys("ai_cache:*")
                    if keys:
                        await self._redis.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis cache clear failed: {e}")
            
            self._local_cache.clear()
        
        logger.info(f"Cache cleared for: {model_type or 'all models'}")
    
    def enable(self) -> None:
        """Enable caching."""
        self._enabled = True
        logger.info("Cache enabled")
    
    def disable(self) -> None:
        """Disable caching."""
        self._enabled = False
        logger.info("Cache disabled")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Cache statistics
        """
        return {
            "enabled": self._enabled,
            "ttl": self._ttl,
            "local_cache_size": len(self._local_cache),
            "redis_connected": self._redis is not None,
        }


# Singleton cache instance
_cache: Optional[ResponseCache] = None


def get_response_cache(redis_client=None) -> ResponseCache:
    """Get or create the singleton response cache.
    
    Args:
        redis_client: Optional Redis client instance
        
    Returns:
        ResponseCache instance
    """
    global _cache
    if _cache is None:
        _cache = ResponseCache(redis_client=redis_client)
        logger.info("Response cache initialized")
    return _cache


# Decorator for caching
def cache_response(model_type: str):
    """Decorator to cache model responses.
    
    Args:
        model_type: Type of model for cache key
        
    Example:
        @cache_response("embedding")
        async def embed_texts(texts: List[str]) -> List[List[float]]:
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = get_response_cache()
            
            # Generate cache key from first argument (usually inputs)
            if args:
                cache_key = args[0]
            else:
                cache_key = kwargs.get('text') or kwargs.get('query') or kwargs.get('inputs')
            
            # Try to get from cache
            cached_result = await cache.get(model_type, cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache.set(model_type, cache_key, result)
            
            return result
        
        return wrapper
    return decorator