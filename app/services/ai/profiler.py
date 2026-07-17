"""Request Profiler - Captures performance metrics for every RAG request.

Profiles:
- Embedding time
- Retrieval time
- Rerank time
- Generation time
- Cache time
- Total time
- Memory usage
- GPU usage
- CPU usage

Uses structured logging (loguru) - no print statements.
"""
import time
import psutil
from typing import Dict, Any, Optional
from contextlib import contextmanager
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class ProfileMetrics:
    """Performance metrics for a single request."""
    
    # Timing (milliseconds)
    embedding_ms: float = 0.0
    retrieval_ms: float = 0.0
    rerank_ms: float = 0.0
    generation_ms: float = 0.0
    cache_ms: float = 0.0
    total_ms: float = 0.0
    
    # Resource usage
    memory_mb: float = 0.0
    gpu_memory_mb: float = 0.0
    cpu_percent: float = 0.0
    
    # Metadata
    request_id: str = ""
    query: str = ""
    cached: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "request_id": self.request_id,
            "timing": {
                "embedding_ms": round(self.embedding_ms, 2),
                "retrieval_ms": round(self.retrieval_ms, 2),
                "rerank_ms": round(self.rerank_ms, 2),
                "generation_ms": round(self.generation_ms, 2),
                "cache_ms": round(self.cache_ms, 2),
                "total_ms": round(self.total_ms, 2),
            },
            "resources": {
                "memory_mb": round(self.memory_mb, 2),
                "gpu_memory_mb": round(self.gpu_memory_mb, 2),
                "cpu_percent": round(self.cpu_percent, 2),
            },
            "metadata": {
                "cached": self.cached,
                "query_length": len(self.query),
            }
        }


class RequestProfiler:
    """Profiles a single RAG request.
    
    Usage:
        profiler = RequestProfiler(request_id="abc123", query="What is X?")
        
        with profiler.profile_section("embedding"):
            # Do embedding
            pass
        
        profiler.log_results()
    """
    
    def __init__(self, request_id: str, query: str):
        """Initialize profiler.
        
        Args:
            request_id: Unique request identifier
            query: User query text
        """
        self.metrics = ProfileMetrics(
            request_id=request_id,
            query=query,
        )
        self._start_time = time.perf_counter()
        self._section_times: Dict[str, float] = {}
    
    @contextmanager
    def profile_section(self, section_name: str):
        """Context manager to profile a section.
        
        Args:
            section_name: Name of section (embedding, retrieval, etc.)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._section_times[section_name] = elapsed_ms
            setattr(self.metrics, f"{section_name}_ms", elapsed_ms)
    
    def mark_cached(self, cached: bool = True):
        """Mark if result was from cache.
        
        Args:
            cached: True if result from cache
        """
        self.metrics.cached = cached
    
    def capture_resources(self):
        """Capture current resource usage."""
        try:
            # CPU usage
            self.metrics.cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            process = psutil.Process()
            self.metrics.memory_mb = process.memory_info().rss / 1024 / 1024
            
            # GPU usage (if available)
            try:
                import torch
                if torch.cuda.is_available():
                    self.metrics.gpu_memory_mb = torch.cuda.memory_allocated() / 1024 / 1024
            except ImportError:
                pass
                
        except Exception as e:
            logger.debug(f"Resource capture failed: {e}")
    
    def finalize(self):
        """Finalize profiling and calculate total time."""
        self.metrics.total_ms = (time.perf_counter() - self._start_time) * 1000
        self.capture_resources()
    
    def log_results(self):
        """Log profiling results with structured logging."""
        self.finalize()
        
        # Structured log with all metrics
        logger.bind(
            event="rag_request",
            **self.metrics.to_dict()
        ).info(
            f"RAG request completed",
            request_id=self.metrics.request_id,
            timing=self.metrics.to_dict()["timing"],
            resources=self.metrics.to_dict()["resources"],
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics dictionary.
        
        Returns:
            Metrics dict
        """
        self.finalize()
        return self.metrics.to_dict()


class GlobalProfiler:
    """Global profiler for tracking aggregate statistics.
    
    Tracks:
    - Total requests
    - Average timings
    - Cache hit rate
    - Error rate
    """
    
    def __init__(self):
        self.total_requests = 0
        self.cache_hits = 0
        self.errors = 0
        
        # Aggregate timings
        self.total_embedding_ms = 0.0
        self.total_retrieval_ms = 0.0
        self.total_rerank_ms = 0.0
        self.total_generation_ms = 0.0
        self.total_cache_ms = 0.0
        self.total_time_ms = 0.0
    
    def record_request(self, metrics: Dict[str, Any]):
        """Record metrics from a request.
        
        Args:
            metrics: Metrics dict from RequestProfiler
        """
        self.total_requests += 1
        
        if metrics.get("metadata", {}).get("cached"):
            self.cache_hits += 1
        
        # Sum timings
        timing = metrics.get("timing", {})
        self.total_embedding_ms += timing.get("embedding_ms", 0)
        self.total_retrieval_ms += timing.get("retrieval_ms", 0)
        self.total_rerank_ms += timing.get("rerank_ms", 0)
        self.total_generation_ms += timing.get("generation_ms", 0)
        self.total_cache_ms += timing.get("cache_ms", 0)
        self.total_time_ms += timing.get("total_ms", 0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics.
        
        Returns:
            Statistics dict
        """
        if self.total_requests == 0:
            return {
                "total_requests": 0,
                "cache_hit_rate": 0.0,
                "error_rate": 0.0,
            }
        
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": self.cache_hits / self.total_requests,
            "errors": self.errors,
            "error_rate": self.errors / self.total_requests,
            "avg_timing_ms": {
                "embedding": self.total_embedding_ms / self.total_requests,
                "retrieval": self.total_retrieval_ms / self.total_requests,
                "rerank": self.total_rerank_ms / self.total_requests,
                "generation": self.total_generation_ms / self.total_requests,
                "cache": self.total_cache_ms / self.total_requests,
                "total": self.total_time_ms / self.total_requests,
            }
        }
    
    def log_stats(self):
        """Log aggregate statistics."""
        stats = self.get_stats()
        
        logger.bind(
            event="profiler_stats",
            **stats
        ).info(
            f"Profiler stats: {stats['total_requests']} requests, "
            f"cache_hit_rate={stats['cache_hit_rate']:.1%}, "
            f"avg_total={stats['avg_timing_ms']['total']:.0f}ms"
        )


# Singleton
_profiler = None


def get_profiler() -> GlobalProfiler:
    """Get or create global profiler.
    
    Returns:
        GlobalProfiler instance
    """
    global _profiler
    if _profiler is None:
        _profiler = GlobalProfiler()
    return _profiler


def create_request_profiler(request_id: str, query: str) -> RequestProfiler:
    """Create a new request profiler.
    
    Args:
        request_id: Unique request identifier
        query: User query text
        
    Returns:
        RequestProfiler instance
    """
    return RequestProfiler(request_id=request_id, query=query)