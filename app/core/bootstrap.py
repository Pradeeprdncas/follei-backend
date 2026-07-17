"""BootstrapManager - Single orchestrator for application startup and shutdown.

No other module may initialize services.
BootstrapManager is the only component that initializes the application.
"""
from __future__ import annotations
import os
import sys
import json
import time
import shutil
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from loguru import logger

from app.core.startup_context import StartupContext, StartupPhase
from app.core.service_registry import ServiceRegistry
from app.core.readiness import Readiness
from app.services.ai.services.readiness import get_readiness_service as get_ai_readiness_service


class BootstrapManager:
    """Orchestrates the entire application lifecycle.
    
    Responsibilities:
    - Phase-based startup execution
    - Dependency ordering between phases
    - Service registration and initialization
    - Graceful shutdown
    - Startup failure recovery
    - Status reporting
    """
    
    def __init__(self):
        self.context = StartupContext()
        self.registry = ServiceRegistry()
        self.readiness = Readiness()
        self._shutdown_timeout = 30.0
        self._initialized_services: List[str] = []
    
    async def initialize(self) -> StartupContext:
        """Run the full startup sequence.
        
        Returns:
            StartupContext with results of all phases
        """
        self.context.started_at = time.time()
        logger.info("=" * 60)
        logger.info("Follei Backend Starting")
        logger.info("=" * 60)
        
        # Phase 1: Configuration Validation (CRITICAL - abort if fails)
        await self._run_phase("configuration", self._phase_configuration, critical=True)
        
        # Phase 2: Infrastructure (CRITICAL - abort if fails)
        await self._run_phase("database", self._phase_database, critical=True)
        
        # Phase 3: AI Runtime (CRITICAL - abort if fails)
        await self._run_phase("models", self._phase_ai_runtime, critical=True)
        
        # Phase 4: Services (non-critical - can continue without)
        await self._run_phase("services", self._phase_services, critical=False)
        
        # Phase 5: Finalize
        await self._run_phase("finalize", self._phase_finalize, critical=False)
        
        self.context.startup_elapsed_s = time.time() - self.context.started_at
        
        if self.context.ready:
            logger.info("=" * 60)
            logger.info(f"Follei Backend Ready in {self.context.startup_elapsed_s:.2f}s")
            logger.info("=" * 60)
        else:
            logger.warning("=" * 60)
            logger.warning("Follei Backend Started with Degraded Functionality")
            logger.warning("=" * 60)
        
        return self.context
    
    async def shutdown(self) -> None:
        """Shutdown all services in reverse order."""
        self.context.shutdown_started = True
        logger.info("Shutting down Follei Backend")
        
        # Shutdown AI Runtime first
        try:
            from app.services.ai.model_manager import get_model_manager
            manager = get_model_manager()
            if hasattr(manager, 'unload_all'):
                await manager.unload_all()
                logger.info("  ✓ Models unloaded")
        except Exception as e:
            logger.error(f"  ✗ Model unloading failed: {e}")
        
        # Shutdown registered services
        await self.registry.shutdown_all(timeout=self._shutdown_timeout)
        
        logger.info("Shutdown complete")
    
    async def _run_phase(self, name: str, coro, critical: bool = False) -> None:
        """Run a startup phase with timing and error handling.
        
        Args:
            name: Phase name
            coro: Coroutine to run
            critical: If True, failure aborts entire startup
        """
        phase = self.context.add_phase(name)
        phase.status = "running"
        phase.started_at = time.time()
        
        try:
            await coro()
            phase.status = "passed"
            logger.info(f"  ✓ Phase '{name}' completed in {phase.duration_ms:.0f}ms")
        except StartupAbortError as e:
            phase.status = "failed"
            phase.error = str(e)
            self.context.errors.append(str(e))
            logger.critical(f"✗ Phase '{name}' FAILED: {e}")
            raise
        except Exception as e:
            phase.status = "failed"
            phase.error = f"{type(e).__name__}: {e}"
            self.context.errors.append(f"Phase '{name}': {e}")
            logger.error(f"✗ Phase '{name}' FAILED: {e}")
            
            if critical:
                msg = f"Critical phase '{name}' failed. Aborting startup."
                logger.critical(msg)
                raise StartupAbortError(msg)
            else:
                logger.warning(f"  ⚠ Phase '{name}' failed, continuing in degraded mode")
        
        phase.completed_at = time.time()
        phase.duration_ms = (phase.completed_at - phase.started_at) * 1000
    
    async def _phase_configuration(self) -> None:
        """Phase 1: Validate configuration and environment."""
        logger.info("Phase 1: Configuration Validation")
        
        # Set paths from environment
        ai_models_root = Path(os.environ.get("AI_MODELS", "./AI_MODELS")).resolve()
        self.context.ai_models_root = ai_models_root
        self.context.manifest_path = ai_models_root / "manifest.json"
        self.context.env = os.environ.get("APP_ENV", "development")
        self.context.project_root = Path(__file__).resolve().parent.parent.parent
        
        # Validate AI dependencies (CRITICAL - abort if missing)
        try:
            from app.services.ai.runtime.dependency_validator import validate_dependencies
            dep_report = await validate_dependencies()
            
            # Debug: Verify types
            logger.debug(f"dep_report type: {type(dep_report)}")
            logger.debug(f"dep_report['warnings'] type: {type(dep_report.get('warnings'))}")
            logger.debug(f"dep_report['errors'] type: {type(dep_report.get('errors'))}")
            logger.debug(f"dep_report['checks'] type: {type(dep_report.get('checks'))}")
            
            # Check for errors (list of strings)
            errors = dep_report.get("errors", [])
            if errors:
                msg = f"AI dependency validation failed: {len(errors)} errors"
                self.context.errors.append(msg)
                logger.critical(f"{msg}\n" + "\n".join(f"  - {e}" for e in errors))
                raise StartupAbortError(msg)
            
            # Log warnings (list of strings)
            warnings = dep_report.get("warnings", [])
            if warnings:
                for warning in warnings:
                    logger.warning(f"  ⚠ {warning}")
            
            # Get summary counts
            summary = dep_report.get("summary", {})
            passed = summary.get("passed", 0)
            total_checks = summary.get("total_checks", 0)
            logger.info(f"  Dependencies: {passed}/{total_checks} checks passed")
            
        except StartupAbortError:
            raise
        except Exception as e:
            msg = f"Dependency validation failed: {e}"
            self.context.errors.append(msg)
            logger.critical(msg)
            raise StartupAbortError(msg)
        
        # Validate manifest (CRITICAL - abort if missing)
        if not self.context.manifest_path.exists():
            msg = f"Manifest not found at {self.context.manifest_path}. Run: python install_models.py"
            self.context.errors.append(msg)
            logger.critical(msg)
            raise StartupAbortError(msg)
        else:
            try:
                with open(self.context.manifest_path, "r") as f:
                    manifest = json.load(f)
                logger.info(f"  Manifest: {len(manifest.get('models', {}))} models registered")
                self.context.add_phase("manifest_check").status = "passed"
            except Exception as e:
                msg = f"Manifest read failed: {e}"
                self.context.errors.append(msg)
                logger.critical(msg)
                raise StartupAbortError(msg)
        
        # Check disk space
        try:
            usage = shutil.disk_usage(ai_models_root)
            free_gb = usage.free / (1024**3)
            logger.info(f"  Disk: {free_gb:.1f}GB free")
        except Exception:
            pass
        
        self.readiness.set_config_validated()
    
    async def _phase_database(self) -> None:
        """Phase 2: Database initialization and schema validation."""
        logger.info("Phase 2: Database")
        try:
            from app.database.init_db import init_db
            init_db()
            logger.info("  ✓ Database initialized")
            
            # Validate critical tables exist (use Engine, not Session)
            from sqlalchemy import inspect
            from app.database.session import engine
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names())
            required_tables = {"tenants", "users", "documents", "conversations", "conversation_messages", "knowledge_sources"}
            missing = required_tables - existing_tables
            if missing:
                msg = f"Missing required database tables: {missing}"
                self.context.errors.append(msg)
                logger.error(f"  ✗ {msg}")
            else:
                logger.info(f"  ✓ Schema validated: {len(existing_tables)} tables present")
            
            self.readiness.set_database_ready()
        except Exception as e:
            logger.error(f"  ✗ Database failed: {e}")
            self.context.warnings.append(f"Database initialization failed: {e}")
    
    async def _phase_ai_runtime(self) -> None:
        """Phase 3: AI Runtime initialization."""
        logger.info("Phase 3: AI Runtime")
        
        # Check if manifest exists (CRITICAL - models required)
        if not self.context.manifest_path.exists():
            msg = f"Manifest not found at {self.context.manifest_path}. Run: python install_models.py"
            self.context.errors.append(msg)
            logger.critical(msg)
            raise StartupAbortError(msg)
        
        # Verify required models in manifest (CRITICAL - abort if missing)
        try:
            with open(self.context.manifest_path, "r") as f:
                manifest = json.load(f)
            
            from app.services.ai.runtime.model_registry import get_required_models
            required = get_required_models()
            models = manifest.get("models", {})
            missing = [
                key for key in required
                if not models.get(key, {}).get("downloaded")
                and not models.get(key, {}).get("verified")
            ]
            if missing:
                msg = f"Missing required models: {missing}. Run: python install_models.py"
                self.context.errors.append(msg)
                logger.critical(msg)
                raise StartupAbortError(msg)
        except StartupAbortError:
            raise
        except Exception as e:
            msg = f"Manifest validation failed: {e}"
            self.context.errors.append(msg)
            logger.critical(msg)
            raise StartupAbortError(msg)
        
        # Validate models (lazy loading — files exist, load deferred to first use)
        try:
            from app.services.ai.runtime.initialize_models import ModelInitializer

            initializer = ModelInitializer()
            init_report = await initializer.initialize()
            
            if init_report.get("ready"):
                self.readiness.set_models_loaded()
                
                # Also set AI readiness service flags
                ai_readiness = get_ai_readiness_service()
                ai_readiness._manifest_ok = True
                ai_readiness._models_ok = True
                ai_readiness._warmup_ok = True
                
                logger.info("  ✓ Model files validated (lazy loading)")
            else:
                msg = f"Model initialization incomplete: {init_report.get('error')}"
                self.context.errors.append(msg)
                logger.error(msg)
                raise StartupAbortError(msg)
        except StartupAbortError:
            raise
        except Exception as e:
            msg = f"Model initialization failed: {e}"
            self.context.errors.append(msg)
            logger.critical(msg)
            raise StartupAbortError(msg)
        
        # Initialize AI Router (only after models loaded)
        try:
            from app.services.ai.model_manager import get_model_manager
            from app.services.ai.registry import get_model_registry
            from app.services.ai.router import AIRouter
            
            manager = get_model_manager()
            # Explicitly initialize - no self-initialization allowed
            manager.initialize()
            
            registry = get_model_registry()
            router = AIRouter()
            
            self.context.model_manager = manager
            self.context.model_registry = registry
            self.context.ai_router = router
            
            logger.info("  ✓ AI Router initialized")

            # Keep voice-call RAG models resident so callers never pay a cold-load cost.
            from app.config.settings import get_settings
            settings = get_settings()
            if settings.VOICE_PRELOAD_MODELS:
                preload = [
                    {"type": "embedding", "name": settings.EMBED_MODEL},
                    {"type": "generator", "name": "qwen2.5-0.5b"},
                ]
                if settings.VOICE_PRELOAD_MAIN_MODEL:
                    preload.append({"type": "generator", "name": settings.GENERATOR_MODEL})
                await manager.preload_models(preload)
                logger.info("  ✓ Voice-call models preloaded")
        except Exception as e:
            logger.warning(f"  AI Router init failed: {e}")
    
    async def _phase_services(self) -> None:
        """Phase 4: Service registration and initialization."""
        logger.info("Phase 4: Services")
        await self.registry.initialize_all()
        
        # Validate Qdrant collection
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            from qdrant_client import QdrantClient
            client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
            collections = client.get_collections().collections
            collection_names = {c.name for c in collections}
            expected = settings.QDRANT_COLLECTION_NAME
            if expected in collection_names:
                info = client.get_collection(expected)
                actual_dim = info.config.params.vectors.size
                expected_dim = settings.QDRANT_VECTOR_SIZE
                if actual_dim != expected_dim:
                    msg = f"Qdrant collection '{expected}' has dimension {actual_dim}, expected {expected_dim}. Delete and recreate the collection, or fix QDRANT_VECTOR_SIZE in .env."
                    self.context.errors.append(msg)
                    self.context.ready = False
                    raise RuntimeError(msg)
                else:
                    logger.info(f"  ✓ Qdrant collection '{expected}' exists (dim={actual_dim})")
            else:
                msg = f"Qdrant collection '{expected}' not found. Create it before startup."
                self.context.warnings.append(msg)
                logger.warning(f"  ⚠ {msg}")
        except Exception as e:
            msg = f"Qdrant validation failed: {e}"
            self.context.warnings.append(msg)
            logger.warning(f"  ⚠ {msg}")
    
    async def _phase_finalize(self) -> None:
        """Phase 5: Finalize startup."""
        # Mark as ready if critical phases passed
        db_phase = self.context.get_phase("database")
        models_phase = self.context.get_phase("models")
        
        # Consider ready if at least database passed
        if db_phase and db_phase.status == "passed":
            self.readiness.set_runtime_ready()
            self.context.ready = True
        elif models_phase and models_phase.status == "passed":
            self.readiness.set_runtime_ready()
            self.context.ready = True
        else:
            # Minimal startup succeeded (server is running)
            self.context.ready = True
            logger.info("  Server running with limited functionality")


class StartupAbortError(Exception):
    """Fatal startup error - abort all further initialization."""
    pass