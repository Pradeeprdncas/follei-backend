"""Regression tests for the lightweight default runtime profile."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CORE_MODULES = (
    "app.main:app",
    "app.workers.indexing_consumer",
    "app.workers.knowledge_sync_consumer",
    "app.workers.google_workspace_worker",
    "app.workers.website_ingestion_worker",
)


def test_core_requirements_exclude_optional_local_ai() -> None:
    requirements = (ROOT / "requirements-core.txt").read_text(encoding="utf-8").lower()

    for package in ("torch", "transformers", "peft", "librosa", "noisereduce"):
        assert not any(
            line.strip().split("=", 1)[0].split("<", 1)[0].split(">", 1)[0] == package
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )


def test_default_launchers_include_exact_core_service_profile() -> None:
    linux_launcher = (ROOT / "start.sh").read_text(encoding="utf-8")
    windows_launcher = (ROOT / "scripts/start_local_runtime.ps1").read_text(
        encoding="utf-8"
    )

    for module in CORE_MODULES:
        module_name = module.split(":", 1)[0]
        assert module in linux_launcher or module_name in linux_launcher
        assert module in windows_launcher or module_name in windows_launcher

    assert "if [[ \"${FULL_PROFILE}\" == \"1\" ]]" in linux_launcher
    assert "if ($Full)" in windows_launcher


def test_importing_core_ai_client_does_not_load_optional_model_stack() -> None:
    code = """
import sys
import app.services.ai.local_llm_client
assert 'app.services.ai.model_manager' not in sys.modules
assert 'torch' not in sys.modules
assert 'transformers' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_removed_duplicate_and_placeholder_backends_stay_removed() -> None:
    assert not (ROOT / "Server_crm-main").exists()
    for module in (
        "analytics_worker.py",
        "communication_worker.py",
        "crm_sync_worker.py",
        "embedding_worker.py",
        "ocr_worker.py",
    ):
        assert not (ROOT / "app" / "workers" / module).exists()
