"""StartupContext - Shared context object passed through initialization.

No module should fetch globals. Everything comes through this context.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class StartupPhase:
    """Result of a single startup phase."""
    name: str
    status: str  # "pending" | "running" | "passed" | "failed" | "skipped"
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StartupContext:
    """Shared context for the entire application lifecycle.
    
    Created once at startup, populated as phases execute.
    Frozen after startup completes.
    """
    
    # ── Configuration ────────────────────────────────────────────────────
    ai_models_root: Path = Path("./AI_MODELS").resolve()
    manifest_path: Path = Path("./AI_MODELS/manifest.json").resolve()
    project_root: Path = Path.cwd()
    env: str = "development"
    
    # ── Phase Results ────────────────────────────────────────────────────
    phases: List[StartupPhase] = field(default_factory=list)
    
    # ── Service References ───────────────────────────────────────────────
    model_manager: Any = None
    ai_router: Any = None
    model_registry: Any = None
    readiness_service: Any = None
    warmup_engine: Any = None
    bootstrap_manager: Any = None
    
    # ── State ────────────────────────────────────────────────────────────
    ready: bool = False
    startup_elapsed_s: float = 0.0
    models_loaded: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    shutdown_started: bool = False
    started_at: float = 0.0
    
    def add_phase(self, name: str) -> StartupPhase:
        """Register a new phase and return it."""
        phase = StartupPhase(name=name, status="pending")
        self.phases.append(phase)
        return phase
    
    def get_phase(self, name: str) -> Optional[StartupPhase]:
        """Get a phase by name."""
        for p in self.phases:
            if p.name == name:
                return p
        return None
    
    def is_healthy(self) -> bool:
        """Overall health based on critical phases."""
        critical = ["configuration", "database", "models"]
        for p in self.phases:
            if p.name in critical and p.status == "failed":
                return False
        return self.ready
    
    def to_report(self) -> Dict[str, Any]:
        """Generate full startup report."""
        return {
            "ready": self.ready,
            "elapsed_s": round(self.startup_elapsed_s, 2),
            "env": self.env,
            "models_loaded": self.models_loaded,
            "phases": [
                {
                    "name": p.name,
                    "status": p.status,
                    "duration_ms": round(p.duration_ms, 1),
                    "error": p.error,
                }
                for p in self.phases
            ],
            "errors": self.errors,
            "warnings": self.warnings,
            "shutdown_started": self.shutdown_started,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
        }