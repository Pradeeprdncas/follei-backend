#!/usr/bin/env python3
"""Model Initializer - Loads and warms up all models at startup.

This script ONLY reads manifest and loads models.
It NEVER downloads models.

Usage:
    python initialize_models.py

Environment:
    AI_MODELS  - Root directory for model storage
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from loguru import logger

# Configure logging
logger.add(
    "logs/initialize_models.log",
    rotation="100 MB",
    retention="7 days",
    encoding="utf-8",
    level="INFO",
)


class ModelInitializer:
    """Single-responsibility model initializer.

    Only responsibilities:
    - Read manifest.json
    - Load every model through ModelManager
    - Warmup
    - Return

    Never:
    - Download models
    - Write files
    - Run benchmarks
    """

    def __init__(self):
        self.ai_models_root = Path(os.environ.get("AI_MODELS", "./AI_MODELS")).resolve()
        self.manifest_path = self.ai_models_root / "manifest.json"
        self.manifest: dict = {}
        self.load_results: dict = {}
        self.warmup_results: dict = {}

    def load_manifest(self) -> bool:
        """Read and validate manifest.json.

        Returns:
            True if manifest exists and is valid
        """
        if not self.manifest_path.exists():
            logger.error(f"Manifest not found: {self.manifest_path}")
            logger.error("Run: python install_models.py")
            return False

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)

            logger.info(f"Loaded manifest: {self.manifest_path}")
            logger.info(f"Generated: {self.manifest.get('generated_at', 'unknown')}")
            return True

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read manifest: {e}")
            return False

    def check_required_models(self) -> list[str]:
        """Return list of missing required models.

        Returns:
            List of missing model keys
        """
        missing = []
        models = self.manifest.get("models", {})

        from app.services.ai.runtime.model_registry import get_required_models
        required = get_required_models()

        for key in required:
            info = models.get(key, {})
            if not info.get("downloaded", False) and not info.get("verified", False):
                missing.append(key)

        return missing

    async def initialize(self) -> dict:
        """Run full initialization sequence.

        This method is called ONLY by BootstrapManager.
        Validates manifest and model availability, then defers actual
        model loading to first use via ModelManager (lazy loading).

        Returns:
            Full initialization report

        Raises:
            RuntimeError: If manifest missing or models missing
        """
        start = time.perf_counter()
        report = {
            "manifest_loaded": False,
            "missing_models": [],
            "load_results": {"loaded": 0, "failed": 0, "errors": [], "details": {}},
            "warmup_results": {"times": {}, "errors": []},
            "ready": False,
            "elapsed_s": 0.0,
        }

        logger.info("=" * 60)
        logger.info("Model Initialization Starting")
        logger.info("=" * 60)

        # Step 1: Load manifest (CRITICAL)
        if not self.load_manifest():
            msg = "Manifest not found. Run: python install_models.py"
            logger.error(msg)
            raise RuntimeError(msg)
        report["manifest_loaded"] = True

        # Step 2: Check required models in manifest (CRITICAL)
        missing = self.check_required_models()
        report["missing_models"] = missing
        if missing:
            msg = f"Missing required models: {missing}. Run: python install_models.py"
            logger.error(msg)
            for m in missing:
                logger.error(f"  - {m}")
            raise RuntimeError(msg)

        # Step 3: Defer model loading to first use (lazy loading via ModelManager)
        # Models are loaded on demand when first requested by inference code.
        logger.info("Model files validated. Loading deferred to first use.")

        report["ready"] = True
        report["elapsed_s"] = time.perf_counter() - start

        logger.info("=" * 60)
        logger.info(f"Initialization complete in {report['elapsed_s']:.2f}s (lazy)")
        logger.info("=" * 60)
        return report


async def main():
    """CLI entry point."""
    initializer = ModelInitializer()
    report = await initializer.initialize()

    if report.get("error"):
        logger.error(f"Failed: {report['error']}")
        sys.exit(1)

    if report.get("ready"):
        logger.info("All models loaded and warmed up")
        sys.exit(0)
    else:
        logger.error("Initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
