"""Health endpoints using BootstrapManager state.

All health data comes from Readiness + StartupContext.
No service discovery. No recursive health checks.
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

# Will be set by BootstrapManager during startup
_context = None
_readiness = None
_bootstrap = None


def set_context(ctx) -> None:
    global _context
    _context = ctx

def set_readiness(r) -> None:
    global _readiness
    _readiness = r

def set_bootstrap(b) -> None:
    global _bootstrap
    _bootstrap = b


def get_liveness() -> Dict[str, Any]:
    """Liveness probe. Always true if process is running."""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


def get_readiness_status() -> Dict[str, Any]:
    """Readiness probe. True only if runtime is ready."""
    ready = _readiness.is_ready if _readiness else False
    report = _readiness.get_report() if _readiness else {"ready": False}
    return {
        "ready": ready,
        "components": report.get("components", {}),
        "timestamp": datetime.utcnow().isoformat(),
    }


def get_startup_status() -> Dict[str, Any]:
    """Startup phase status."""
    if _context:
        return _context.to_report()
    return {"ready": False, "phases": []}


def get_dependency_health() -> Dict[str, Any]:
    """Dependency health from service registry."""
    return {"status": "check_disabled_during_lifespan"}


def get_model_status() -> Dict[str, Any]:
    """Model status."""
    if _context:
        return {
            "models_loaded": _context.models_loaded,
            "phases": [
                {"name": p.name, "status": p.status}
                for p in _context.phases
                if "model" in p.name.lower()
            ],
        }
    return {"models_loaded": 0}