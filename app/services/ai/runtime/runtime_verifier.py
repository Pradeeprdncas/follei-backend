"""Runtime Verifier - Startup model verification sequence.

When FastAPI starts, verifies:
AI_MODELS → Embeddings → Classifier → Generator → Summarizer → Reranker
→ LoRA → Tokenizer → Warmup → Ready

If any model is missing, shows exactly:
- Missing model
- Expected path
- Required repository
- Suggested fix
"""
import asyncio
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.runtime.download_models import (
    ModelDownloader,
    get_model_downloader,
    MODEL_INVENTORY,
)

_settings = get_settings()


class RuntimeVerifier:
    """Verifies all AI models are present and loadable on startup.

    Performs a complete verification chain:
    1. AI_MODELS root exists
    2. All model directories exist with required files
    3. Models can be loaded (verify with ModelManager)
    4. Tokenizers are available
    5. Warmup inference succeeds
    6. Everything is ready
    """

    def __init__(self):
        self._ai_models_root = Path(_settings.AI_MODELS)
        self._verification_results: Dict[str, Dict] = {}
        self._startup_time: float = 0.0
        self._all_ready = False

    @property
    def is_ready(self) -> bool:
        return self._all_ready

    @property
    def startup_time(self) -> float:
        return self._startup_time

    async def verify_and_prepare(
        self, download_if_missing: bool = True, warmup: bool = True
    ) -> Dict[str, Any]:
        """Run the full verification chain.

        Args:
            download_if_missing: Whether to attempt downloading missing models
            warmup: Whether to warm up models after verification

        Returns:
            Complete verification report
        """
        start = time.perf_counter()
        logger.info("=" * 60)
        logger.info("AI Runtime Verification Starting...")
        logger.info("=" * 60)

        report = {
            "start_time": start,
            "ai_models_root": str(self._ai_models_root),
            "root_exists": self._ai_models_root.exists(),
            "steps": [],
            "models": {},
            "all_ready": False,
            "missing_models": [],
            "errors": [],
            "startup_time_s": 0.0,
            "device": self._detect_device(),
            "gpu_info": self._get_gpu_info(),
        }

        # Step 1: Verify AI_MODELS root
        if not self._ai_models_root.exists():
            msg = f"AI_MODELS root not found: {self._ai_models_root}"
            logger.error(msg)
            report["errors"].append(msg)
            report["all_ready"] = False
            report["startup_time_s"] = time.perf_counter() - start
            self._all_ready = False
            self._startup_time = time.perf_counter() - start
            return report

        report["steps"].append({"step": "ai_models_root", "status": "ok"})

        # Step 2: Download/verify all models
        downloader = get_model_downloader()
        logger.info("Step 1/6: Verifying model downloads...")
        if download_if_missing:
            verify_results = await downloader.ensure_all()
        else:
            verify_results = await downloader.verify_all()

        report["steps"].append(
            {
                "step": "model_downloads",
                "status": "ok",
                "models_verified": len(verify_results),
            }
        )

        # Check for missing models
        missing = []
        for key, status in verify_results.items():
            report["models"][key] = status
            if not status.get("exists", False):
                missing.append(key)
                report["steps"].append(
                    {
                        "step": f"model:{key}",
                        "status": "missing",
                        "path": status.get("path", "?"),
                        "suggested_fix": status.get(
                            "suggested_fix",
                            f"Download {key} manually",
                        ),
                    }
                )
            else:
                report["steps"].append(
                    {
                        "step": f"model:{key}",
                        "status": "present",
                        "size_mb": status.get("size_bytes", 0) / (1024 * 1024),
                    }
                )

        if missing:
            logger.error(f"Missing models: {missing}")
            for m in missing:
                s = verify_results.get(m, {})
                logger.error(
                    f"  - {m}: expected at {s.get('path', '?')}, "
                    f"repo: {s.get('repo', '?')}"
                )
                if s.get("suggested_fix"):
                    logger.error(f"    Fix: {s['suggested_fix']}")

            report["missing_models"] = missing
            report["errors"].append(f"Missing {len(missing)} model(s)")

            # Step 3: Try to load available models anyway
            logger.info("Step 2/6: Attempting to load available models...")
        else:
            logger.info("Step 2/6: All models present ✓")

        # Step 3: Load models via ModelManager
        logger.info("Step 3/6: Loading models...")
        load_results = await self._load_models_via_manager()
        report["load_results"] = load_results
        report["steps"].append(
            {
                "step": "model_loading",
                "status": "ok" if not load_results.get("errors") else "partial",
                "loaded": load_results.get("loaded", 0),
                "failed": load_results.get("failed", 0),
            }
        )

        # Step 4: Warm up models
        if warmup:
            logger.info("Step 4/6: Warming up models...")
            warmup_results = await self._warmup_models()
            report["warmup_results"] = warmup_results
            report["steps"].append(
                {
                    "step": "model_warmup",
                    "status": "ok" if not warmup_results.get("errors") else "partial",
                    "warm_times": warmup_results.get("warm_times", {}),
                }
            )
        else:
            report["steps"].append({"step": "model_warmup", "status": "skipped"})

        # Step 5: Verify memory/GPU state
        logger.info("Step 5/6: Checking memory and device state...")
        memory_info = self._get_memory_info()
        report["memory"] = memory_info
        report["steps"].append(
            {
                "step": "memory_check",
                "status": "ok",
                "ram_gb": memory_info.get("ram_gb", 0),
                "vram_gb": memory_info.get("vram_gb", 0),
            }
        )

        # Step 6: Final status
        logger.info("Step 6/6: Finalizing...")
        elapsed = time.perf_counter() - start
        all_ready = (
            len(missing) == 0
            and load_results.get("failed", 0) == 0
            and (not warmup or not warmup_results.get("errors"))
        )
        report["all_ready"] = all_ready
        report["startup_time_s"] = elapsed
        report["steps"].append(
            {
                "step": "complete",
                "status": "ready" if all_ready else "degraded",
                "elapsed_s": elapsed,
            }
        )

        if all_ready:
            logger.info("=" * 60)
            logger.info(f"✓ AI Runtime Ready in {elapsed:.2f}s")
            logger.info("=" * 60)
        else:
            logger.warning("=" * 60)
            logger.warning(f"⚠ AI Runtime started in degraded mode ({elapsed:.2f}s)")
            logger.warning("Missing models will fallback to cloud API")
            logger.warning("=" * 60)

        self._verification_results = report
        self._all_ready = all_ready
        self._startup_time = elapsed
        return report

    async def _load_models_via_manager(self) -> Dict[str, Any]:
        """Try to load all models through ModelManager."""
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        results = {"loaded": 0, "failed": 0, "errors": [], "details": {}}

        model_configs = [
            ("embedding", _settings.EMBED_MODEL),
            ("query_optimizer", _settings.QUERY_MODEL),
            ("summarizer", _settings.SUMMARY_MODEL),
            ("reranker", _settings.RERANK_MODEL),
            ("generator", _settings.GENERATOR_MODEL),
            ("classifier", _settings.INTENT_MODEL),
        ]

        for model_type, model_name in model_configs:
            try:
                key = f"{model_type}:{model_name}"
                logger.info(f"  Loading {key}...")
                info = await manager.get_model(model_type, model_name)
                results["details"][key] = {
                    "loaded": True,
                    "has_tokenizer": info.get("tokenizer") is not None,
                    "device": str(info.get("model", {}).get("device", "?")),
                }
                results["loaded"] += 1
                logger.info(f"  ✓ {key} loaded")
            except Exception as e:
                logger.warning(f"  ✗ {model_type}:{model_name} load failed: {e}")
                results["failed"] += 1
                results["errors"].append(f"{model_type}:{model_name}: {e}")
                results["details"][f"{model_type}:{model_name}"] = {
                    "loaded": False,
                    "error": str(e),
                }

        return results

    async def _warmup_models(self) -> Dict[str, Any]:
        """Run warmup inference on all loaded models."""
        from app.services.ai.model_warmup import get_model_warmup

        warmup = get_model_warmup()
        results = {"warm_times": {}, "errors": []}

        try:
            await warmup.warmup_all()
            results["warm_times"] = warmup.get_warmup_times()
            # Record tokenizer latency and memory
            for key, time_s in results["warm_times"].items():
                logger.info(f"  {key} warmup: {time_s:.2f}s")
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            results["errors"].append(str(e))

        return results

    def _detect_device(self) -> str:
        """Detect available device (cuda/cpu/mps)."""
        try:
            import torch

            if torch.cuda.is_available():
                return f"cuda:{torch.cuda.current_device()}"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        except ImportError:
            return "cpu"

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU information if available."""
        info = {"available": False, "name": None, "total_vram_gb": 0}
        try:
            import torch

            if torch.cuda.is_available():
                info["available"] = True
                info["name"] = torch.cuda.get_device_name(0)
                info["total_vram_gb"] = (
                    torch.cuda.get_device_properties(0).total_memory / (1024**3)
                )
        except ImportError:
            pass
        return info

    def _get_memory_info(self) -> Dict[str, Any]:
        """Get current memory usage."""
        info = {"ram_gb": 0, "vram_gb": 0, "ram_percent": 0}
        try:
            import psutil

            mem = psutil.virtual_memory()
            info["ram_gb"] = mem.total / (1024**3)
            info["ram_percent"] = mem.percent
        except ImportError:
            pass

        try:
            import torch

            if torch.cuda.is_available():
                info["vram_gb"] = (
                    torch.cuda.memory_allocated(0) / (1024**3)
                )
        except ImportError:
            pass

        return info

    def get_verification_report(self) -> Dict[str, Any]:
        """Get the complete verification report."""
        return self._verification_results


# Singleton
_verifier: Optional["RuntimeVerifier"] = None


def get_runtime_verifier() -> RuntimeVerifier:
    """Get or create singleton runtime verifier."""
    global _verifier
    if _verifier is None:
        _verifier = RuntimeVerifier()
    return _verifier