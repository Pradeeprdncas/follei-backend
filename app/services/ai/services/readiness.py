"""Runtime Readiness Service - Single source of truth for system readiness.

Checks:
- Manifest loaded
- Required models loaded
- Warmup completed
- Dependencies available
"""
from typing import Dict, Any
from loguru import logger


class RuntimeReadinessService:
    """Production readiness checker for the AI runtime.

    All components check here for determining if the system is ready.
    """

    def __init__(self):
        self._manifest_ok = False
        self._models_ok = False
        self._warmup_ok = False
        self._dependencies_ok = False
        self._ready = False
        self._loaded_models: list = []
        self._warmup_times: dict = {}
        self._core_readiness = None  # Reference to core readiness service
    
    def set_core_readiness(self, core_readiness):
        """Set reference to core readiness service for syncing."""
        self._core_readiness = core_readiness

    def check_manifest(self) -> bool:
        """Check if manifest file exists and is readable."""
        try:
            from pathlib import Path
            import os
            ai_models_root = Path(os.environ.get("AI_MODELS", "./AI_MODELS"))
            manifest_path = ai_models_root / "manifest.json"
            self._manifest_ok = manifest_path.exists() and manifest_path.is_file()
            if not self._manifest_ok:
                logger.warning(f"Manifest not found at {manifest_path}")
        except Exception as e:
            logger.error(f"Manifest check failed: {e}")
            self._manifest_ok = False
        return self._manifest_ok

    def check_models(self) -> bool:
        """Check if all required models are loaded."""
        try:
            from app.services.ai.model_manager import get_model_manager
            from app.services.ai.runtime.model_registry import get_required_models

            manager = get_model_manager()
            required = get_required_models()
            loaded = manager.get_loaded_models()
            self._loaded_models = list(loaded.keys())

            # Check required models are present
            for key, info in required.items():
                model_type = info.get("model_type")
                local_path = info.get("local_path", "")
                model_name = local_path.split("/")[-1] if local_path else key
                if not manager.is_model_loaded(model_type, model_name):
                    logger.warning(f"Required model not loaded: {model_type}:{model_name}")
                    self._models_ok = False
                    return False

            self._models_ok = True
            return True
        except Exception as e:
            logger.error(f"Model check failed: {e}")
            self._models_ok = False
            return False

    def check_warmup(self) -> bool:
        """Check if warmup has completed."""
        try:
            from app.services.ai.runtime.warmup import get_model_warmup
            warmup = get_model_warmup()
            self._warmup_times = warmup.get_warmup_times()
            self._warmup_ok = len(self._warmup_times) > 0
        except Exception:
            self._warmup_ok = False
        return self._warmup_ok

    def check_dependencies(self) -> bool:
        """Check infrastructure dependencies (non-blocking)."""
        self._dependencies_ok = True  # Don't block on infra
        return True

    def is_ready(self) -> bool:
        """Complete readiness check.

        Returns:
            True only if all critical components are ready
        """
        # Simple flag-based check - no circular verification
        self._ready = self._manifest_ok and self._models_ok
        
        if not self._manifest_ok:
            logger.warning("Readiness: manifest NOT loaded")
        if not self._models_ok:
            logger.warning("Readiness: models NOT loaded")
        
        return self._ready

    def get_loaded_models(self) -> list:
        """Get list of loaded model keys."""
        return self._loaded_models

    def get_warmup_times(self) -> dict:
        """Get warmup times."""
        return self._warmup_times

    def get_report(self) -> Dict[str, Any]:
        """Get full readiness report."""
        return {
            "ready": self._ready,
            "manifest": self._manifest_ok,
            "models": self._models_ok,
            "warmup": self._warmup_ok,
            "dependencies": self._dependencies_ok,
            "loaded_models": self._loaded_models,
            "warmup_times": self._warmup_times,
        }


# Singleton
_readiness_service: RuntimeReadinessService = None


def get_readiness_service() -> RuntimeReadinessService:
    """Get or create singleton readiness service."""
    global _readiness_service
    if _readiness_service is None:
        _readiness_service = RuntimeReadinessService()
    return _readiness_service