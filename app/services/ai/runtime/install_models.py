#!/usr/bin/env python3
"""Model Installer - Downloads and verifies all required models.

This script ONLY downloads models, writes manifest.json, and copies LoRAs.
It NEVER loads models, runs inference, benchmarks, or warms up.

Usage:
    python install_models.py

Environment:
    AI_MODELS  - Root directory for model storage
    HF_TOKEN   - HuggingFace token for private models
    OFFLINE    - Set to 1 for offline mode (skip downloads)
"""
import asyncio
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger
from app.services.ai.runtime.download_models import MODEL_INVENTORY

# Configure logging
logger.add(
    "logs/install_models.log",
    rotation="100 MB",
    retention="7 days",
    encoding="utf-8",
    level="INFO",
)


class ModelInstaller:
    """Single-responsibility model installer.

    Only responsibilities:
    - Create required directories
    - Read model registry
    - Download missing models
    - Resume interrupted downloads
    - Verify downloads
    - Write manifest.json
    - Copy LoRAs

    Never:
    - Load any model
    - Run inference
    - Benchmark
    - Warmup
    """

    def __init__(self):
        self.ai_models_root = Path(os.environ.get("AI_MODELS", "./AI_MODELS")).resolve()
        self.hf_token = os.environ.get("HF_TOKEN")
        print(self.hf_token)
        self.offline = os.environ.get("OFFLINE", "0") == "1"
        self.cache_dir = self.ai_models_root / "cache"
        self.hf_home = os.environ.get(
            "HF_HOME",
            str(self.cache_dir / "huggingface"),
        )
        self.results: Dict[str, Dict] = {}
        self.errors: List[str] = []

    def create_directories(self) -> None:
        """Create all required model directories."""
        dirs = [
            self.ai_models_root,
            self.ai_models_root / "embeddings",
            self.ai_models_root / "llms",
            self.ai_models_root / "rerankers",
            self.ai_models_root / "classifiers",
            self.ai_models_root / "summarizers",
            self.ai_models_root / "query_optimizers",
            self.ai_models_root / "verification",
            self.ai_models_root / "planner",
            self.ai_models_root / "loras",
            self.cache_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created/verified directory: {d}")
        logger.info(f"Model directories ready at {self.ai_models_root}")

    async def install_all(self, force_redownload: bool = False) -> Dict[str, Dict]:
        """Install all models and LoRAs.

        Args:
            force_redownload: Force re-download even if present

        Returns:
            Status dict for each model/LoRA
        """
        if self.offline:
            logger.warning("Offline mode enabled - skipping downloads")
            await self._verify_existing()
            return self.results

        self.create_directories()

        from app.services.ai.runtime.model_registry import list_all_models
        from app.services.ai.runtime.download_models import (
            ModelDownloader,
            get_model_downloader,
            MODEL_INVENTORY,
            LORA_PATHS,
        )

        downloader = get_model_downloader()

        # Process standard models
        for model_key in MODEL_INVENTORY:
            await self._install_model(model_key, downloader, force_redownload)

        # Process LoRAs
        for lora_key in LORA_PATHS:
            await self._install_lora(lora_key, downloader, force_redownload)

        self.write_manifest()
        return self.results

    async def _install_model(self, model_key: str, downloader, force: bool = False) -> None:
        """Install a single base model."""
        info = MODEL_INVENTORY.get(model_key)
        if not info:
            raise ValueError(f"Unknown model key: {model_key}")

        repo_id = info["repo"]
        subdir = info["subdir"]
        dest = self.ai_models_root / subdir

        # Verify if already present
        if dest.exists() and not force:
            status = await downloader._verify_model(model_key, dest, info["files"])
            if status.get("exists", False):
                logger.info(f"Skipping {model_key} (already installed)")
                size_mb = status.get("size_bytes", 0) / (1024 * 1024)
                self.results[model_key] = {
                    "action": "skipped",
                    "exists": True,
                    "path": str(dest),
                    "size_mb": size_mb,
                }
                return

        # Download
        logger.info(f"Downloading {repo_id} -> {subdir}")
        start = time.perf_counter()
        try:
            success = await downloader._download_model(model_key, force=force)
            if not success:
                raise RuntimeError(f"Download failed: {model_key}")
        except Exception as e:
            logger.error(f"Failed to download {model_key}: {e}")
            self.results[model_key] = {
                "action": "download_failed",
                "exists": False,
                "error": str(e),
                "path": str(dest),
            }
            self.errors.append(f"{model_key}: {e}")
            return

        # Verify downloaded files
        status = await downloader._verify_model(model_key, dest, info["files"])
        if not status.get("exists", False):
            missing = status.get("files_missing", [])
            raise RuntimeError(f"Download incomplete, missing: {missing}")
        size_mb = status.get("size_bytes", 0) / (1024 * 1024)
        elapsed = time.perf_counter() - start
        logger.info(f"✓ {model_key} downloaded ({size_mb:.1f} MB in {elapsed:.1f}s)")

        self.results[model_key] = {
            "action": "downloaded",
            "exists": True,
            "path": str(dest),
            "size_mb": size_mb,
            "download_time_s": elapsed,
        }

    async def _install_lora(self, lora_key: str, downloader, force: bool = False) -> None:
        """Install a single LoRA by copying from source."""
        info = LORA_PATHS.get(lora_key)
        if not info:
            raise ValueError(f"Unknown LoRA key: {lora_key}")

        source = Path(info["source"])
        dest = self.ai_models_root / info["dest_subdir"]

        if not source.exists():
            logger.warning(f"LoRA source not found: {source}. Skipping {lora_key}")
            self.results[f"lora:{lora_key}"] = {
                "action": "skipped",
                "exists": False,
                "error": "Source not found",
            }
            return

        if dest.exists() and not force:
            logger.info(f"Skipping LoRA {lora_key} (already installed)")
            self.results[f"lora:{lora_key}"] = {
                "action": "skipped",
                "exists": True,
                "path": str(dest),
            }
            return

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
        logger.info(f"✓ LoRA {lora_key} copied ({size_mb:.1f} MB)")

        self.results[f"lora:{lora_key}"] = {
            "action": "installed",
            "exists": True,
            "path": str(dest),
            "size_mb": size_mb,
        }

    async def _verify_existing(self) -> None:
        """Verify what's already present when offline."""
        from app.services.ai.runtime.download_models import (
            ModelDownloader,
            get_model_downloader,
            MODEL_INVENTORY,
            LORA_PATHS,
        )

        downloader = get_model_downloader()
        results = await downloader.verify_all()
        self.results = results

    def write_manifest(self) -> None:
        """Write/manifest.json with current state of all models."""
        manifest_path = self.ai_models_root / "manifest.json"
        manifest = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ai_models_root": str(self.ai_models_root),
            "models": {},
        }

        for key, status in self.results.items():
            if key.startswith("lora:"):
                continue
            manifest["models"][key] = {
                "repo": MODEL_INVENTORY.get(key, {}).get("repo", "unknown"),
                "path": MODEL_INVENTORY.get(key, {}).get("subdir", ""),
                "downloaded": status.get("exists", False),
                "verified": status.get("exists", False),
                "size": f"{status.get('size_mb', 0):.0f}MB",
            }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Manifest written: {manifest_path}")


async def main():
    """CLI entry point."""
    installer = ModelInstaller()
    force = "--force" in os.sys.argv
    logger.info("=" * 60)
    logger.info("Model Installation Starting")
    logger.info("=" * 60)
    results = await installer.install_all(force_redownload=force)
    logger.info("=" * 60)

    failed = [k for k, v in results.items() if not v.get("exists", False)]
    if failed:
        logger.error(f"Failed/skipped: {fail=}")
        for f in failed:
            logger.error(f"  - {f}")
        raise SystemExit(1)

    logger.info("All models installed successfully")
    logger.info("Next: python initialize_models.py")


if __name__ == "__main__":
    asyncio.run(main())