"""Readiness - Simple state-based readiness tracking.

Readiness is SET by BootstrapManager during startup.
Readiness never discovers system state itself.
Readiness only stores and reports state.
"""
from __future__ import annotations
from typing import Dict, Any


class Readiness:
    """Simple state-based readiness tracker.
    
    Readiness is SET by BootstrapManager after each phase.
    Health endpoints QUERY this class for state.
    No recursive checking. No circular dependencies.
    """
    
    def __init__(self):
        self._manifest_loaded: bool = False
        self._config_validated: bool = False
        self._database_ready: bool = False
        self._models_loaded: bool = False
        self._warmup_complete: bool = False
        self._runtime_ready: bool = False
        self._healthy: bool = False
    
    def set_config_validated(self) -> None:
        self._config_validated = True
    
    def set_database_ready(self) -> None:
        self._database_ready = True
    
    def set_manifest_loaded(self) -> None:
        self._manifest_loaded = True
    
    def set_models_loaded(self) -> None:
        self._models_loaded = True
    
    def set_warmup_complete(self) -> None:
        self._warmup_complete = True
    
    def set_runtime_ready(self) -> None:
        self._runtime_ready = True
        self._healthy = True
    
    def set_unhealthy(self) -> None:
        self._healthy = False
    
    @property
    def is_ready(self) -> bool:
        return self._runtime_ready
    
    @property
    def is_healthy(self) -> bool:
        return self._healthy
    
    @property
    def is_live(self) -> bool:
        return True  # Process is alive
    
    def get_report(self) -> Dict[str, Any]:
        """Get full readiness report."""
        return {
            "ready": self._runtime_ready,
            "healthy": self._healthy,
            "components": {
                "config": self._config_validated,
                "database": self._database_ready,
                "manifest": self._manifest_loaded,
                "models": self._models_loaded,
                "warmup": self._warmup_complete,
            },
        }