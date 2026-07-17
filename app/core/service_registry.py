"""ServiceRegistry - Centralized service registration and lifecycle.

Responsibilities:
- register services
- resolve services by name/type
- initialize all registered services
- shutdown all services in reverse order
- health check all services
"""
from __future__ import annotations
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, TypeVar
from dataclasses import dataclass, field
from loguru import logger


T = TypeVar("T")


class ManagedService(Protocol):
    """Protocol for services with lifecycle management."""
    
    async def initialize(self) -> None:
        ...
    
    async def health(self) -> dict:
        ...
    
    async def shutdown(self) -> None:
        ...


@dataclass
class ServiceEntry:
    """Registered service entry."""
    name: str
    instance: Any
    dependencies: List[str] = field(default_factory=list)
    initialized: bool = False
    initialize_time_ms: float = 0.0
    shutdown_time_ms: float = 0.0


class ServiceRegistry:
    """Central registry for all application services.
    
    No globals. No module-level singletons.
    The registry is the single source of truth for service instances.
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceEntry] = {}
        self._factories: Dict[str, Callable] = {}
    
    def register(
        self,
        name: str,
        instance: Any,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Register a service instance.
        
        Args:
            name: Unique service identifier
            instance: Service instance
            dependencies: Names of services this depends on
        """
        if name in self._services:
            raise ValueError(f"Service '{name}' already registered")
        self._services[name] = ServiceEntry(
            name=name,
            instance=instance,
            dependencies=dependencies or [],
        )
        logger.debug(f"Registered service: {name}")
    
    def register_factory(self, name: str, factory: Callable) -> None:
        """Register a factory for lazy service creation."""
        self._factories[name] = factory
    
    def resolve(self, name: str) -> Any:
        """Resolve a service by name."""
        if name in self._services:
            return self._services[name].instance
        if name in self._factories:
            instance = self._factories[name]()
            self._services[name] = ServiceEntry(name=name, instance=instance)
            return instance
        raise KeyError(f"Service '{name}' not found in registry")
    
    def get(self, name: str, default: Any = None) -> Any:
        """Safely get a service, returning default if not found."""
        try:
            return self.resolve(name)
        except KeyError:
            return default
    
    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services or name in self._factories
    
    @property
    def names(self) -> List[str]:
        """Get all registered service names."""
        return list(self._services.keys())
    
    @property
    def initialized_count(self) -> int:
        """Count of initialized services."""
        return sum(1 for s in self._services.values() if s.initialized)
    
    async def initialize_all(self) -> Dict[str, Dict]:
        """Initialize all registered services respecting dependencies.
        
        Returns:
            Dict of service name -> result
        """
        results: Dict[str, Dict] = {}
        
        # Topological sort by dependencies
        sorted_services = self._topological_sort()
        
        for name in sorted_services:
            entry = self._services[name]
            if entry.initialized:
                continue
            
            # Ensure dependencies initialized
            for dep in entry.dependencies:
                if dep in self._services and not self._services[dep].initialized:
                    dep_result = await self._initialize_one(dep)
                    results[dep] = dep_result
            
            result = await self._initialize_one(name)
            results[name] = result
        
        return results
    
    async def _initialize_one(self, name: str) -> Dict:
        """Initialize a single service."""
        entry = self._services[name]
        instance = entry.instance
        
        if hasattr(instance, 'initialize') and callable(instance.initialize):
            try:
                t0 = time.perf_counter()
                if hasattr(instance.initialize, '__await__') or hasattr(instance.initialize, '__call__'):
                    result = instance.initialize()
                    if hasattr(result, '__await__'):
                        await result
                elapsed = time.perf_counter() - t0
                entry.initialized = True
                entry.initialize_time_ms = round(elapsed * 1000, 1)
                logger.info(f"  ✓ {name} initialized ({entry.initialize_time_ms}ms)")
                return {"status": "ok", "time_ms": entry.initialize_time_ms}
            except Exception as e:
                logger.error(f"  ✗ {name} failed: {e}")
                return {"status": "failed", "error": str(e)}
        
        entry.initialized = True
        return {"status": "ok", "time_ms": 0}
    
    async def shutdown_all(self, timeout: float = 30.0) -> Dict[str, Dict]:
        """Shutdown all services in reverse initialization order.
        
        Args:
            timeout: Maximum time to wait for all services to shutdown
            
        Returns:
            Dict of service name -> shutdown result
        """
        results: Dict[str, Dict] = {}
        ordered = list(reversed(self._services.keys()))
        
        for name in ordered:
            entry = self._services[name]
            if not entry.initialized:
                continue
            
            instance = entry.instance
            if hasattr(instance, 'shutdown') and callable(instance.shutdown):
                try:
                    t0 = time.perf_counter()
                    result = instance.shutdown()
                    if hasattr(result, '__await__'):
                        await result
                    elapsed = time.perf_counter() - t0
                    entry.shutdown_time_ms = round(elapsed * 1000, 1)
                    logger.info(f"  ✓ {name} shut down ({entry.shutdown_time_ms}ms)")
                    results[name] = {"status": "ok", "time_ms": entry.shutdown_time_ms}
                except Exception as e:
                    logger.error(f"  ✗ {name} shutdown failed: {e}")
                    results[name] = {"status": "failed", "error": str(e)}
        
        return results
    
    async def health_all(self) -> Dict[str, Dict]:
        """Get health of all initialized services."""
        results: Dict[str, Dict] = {}
        
        for name, entry in self._services.items():
            if not entry.initialized:
                results[name] = {"status": "not_initialized"}
                continue
            
            instance = entry.instance
            if hasattr(instance, 'health') and callable(instance.health):
                try:
                    result = instance.health()
                    if hasattr(result, '__await__'):
                        result = await result
                    results[name] = result if isinstance(result, dict) else {"status": str(result)}
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
            else:
                results[name] = {"status": "ok"}
        
        return results
    
    def _topological_sort(self) -> List[str]:
        """Sort services by dependency order."""
        sorted_names: List[str] = []
        visited: set = set()
        
        def visit(name: str, path: set):
            if name in path:
                raise ValueError(f"Circular dependency detected: {name}")
            if name in visited:
                return
            path.add(name)
            if name in self._services:
                for dep in self._services[name].dependencies:
                    visit(dep, path)
                visited.add(name)
                sorted_names.append(name)
            path.remove(name)
        
        for name in self._services:
            visit(name, set())
        
        return sorted_names
    
    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()
        self._factories.clear()