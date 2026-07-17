"""Dependency Validator - Validates all AI dependencies at startup.

Checks:
- Python packages installed
- Model files exist
- GPU/CUDA available (optional)
- Config files valid

Fails startup immediately if critical dependencies missing.
"""
from typing import Dict, Any, List, TypedDict
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.model_policy import ALLOWED_MODELS

_settings = get_settings()


class DependencyReport(TypedDict):
    """Type-safe structure for dependency validation report.
    
    This TypedDict ensures all callers receive consistent data structures.
    """
    checks: Dict[str, Dict[str, Any]]
    warnings: List[str]
    errors: List[str]
    summary: Dict[str, Any]


def clean_version(version: str) -> str:
    """Strip build metadata from version string.
    
    Args:
        version: Version string (e.g., "2.12.1+cpu", "2.10.0+cu124")
        
    Returns:
        Cleaned version (e.g., "2.12.1", "2.10.0")
    """
    return version.split("+")[0]


def _compare_versions(installed: str, required: str) -> bool:
    """Compare two version strings using semantic versioning.
    
    Args:
        installed: Installed version (e.g., "2.12.1+cpu")
        required: Required version (e.g., "2.0.0")
        
    Returns:
        True if installed >= required
        
    Examples:
        >>> _compare_versions("2.12.1+cpu", "2.0.0")
        True
        >>> _compare_versions("2.1.0", "2.0.0")
        True
        >>> _compare_versions("1.13.1", "2.0.0")
        False
        >>> _compare_versions("2.10.0", "2.9.0")
        True
        >>> _compare_versions("2.9.0", "2.10.0")
        False
    """
    try:
        from packaging.version import Version
        
        installed_clean = clean_version(installed)
        required_clean = clean_version(required)
        
        installed_ver = Version(installed_clean)
        required_ver = Version(required_clean)
        
        return installed_ver >= required_ver
        
    except Exception as e:
        logger.warning(f"Version comparison failed: {e}, falling back to string comparison")
        # Fallback to string comparison (should not happen)
        return installed >= required


class DependencyValidator:
    """Validates all AI/ML dependencies at startup.
    
    Critical dependencies: Must be present or startup fails
    Optional dependencies: Warning only, graceful degradation
    """
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks: Dict[str, Dict[str, Any]] = {}
    
    async def validate_all(self) -> DependencyReport:
        """Run all validation checks.
        
        Returns:
            DependencyReport with checks, warnings, errors, and summary
            
        Raises:
            RuntimeError: If critical dependencies missing
        """
        logger.info("Validating AI dependencies...")
        
        # Check Python packages
        await self._check_python_packages()
        
        # Check model files
        await self._check_model_files()
        
        # Check GPU (optional)
        await self._check_gpu()
        
        # Check manifest
        await self._check_manifest()
        
        # Build report with CONSISTENT structure
        report = self._build_report()
        
        # Fail if critical errors
        if self.errors:
            error_msg = "Critical dependency validation failed:\n" + "\n".join(
                f"  - {e}" for e in self.errors
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)
        
        if self.warnings:
            warning_msg = "Dependency warnings:\n" + "\n".join(
                f"  - {w}" for w in self.warnings
            )
            logger.warning(warning_msg)
        
        logger.info(f"Dependency validation passed: {report['summary']['total_checks']} checks, {report['summary']['error_count']} errors, {report['summary']['warning_count']} warnings")
        return report
    
    async def _check_python_packages(self) -> None:
        """Check required Python packages."""
        logger.debug("Checking Python packages...")
        
        # Critical packages
        critical_packages = {
            "torch": "2.0.0",
            "transformers": "4.30.0",
            "sentence_transformers": "2.2.0",
        }
        
        # Optional packages
        optional_packages = {
            "peft": "0.4.0",
        }
        
        # Check critical packages
        for package, min_version in critical_packages.items():
            check_name = f"package:{package}"
            try:
                if package == "sentence_transformers":
                    import sentence_transformers
                    version = sentence_transformers.__version__
                elif package == "torch":
                    import torch
                    version = torch.__version__
                elif package == "transformers":
                    import transformers
                    version = transformers.__version__
                else:
                    module = __import__(package)
                    version = getattr(module, "__version__", "unknown")
                
                # Check version using semantic versioning
                version_ok = _compare_versions(version, min_version)
                normalized = clean_version(version)
                
                if version_ok:
                    self.checks[check_name] = {
                        "status": "ok",
                        "version": version,
                        "normalized": normalized,
                        "required": f">={min_version}",
                    }
                    logger.info(
                        f"Installed {package} : {version}\n"
                        f"  Normalized      : {normalized}\n"
                        f"  Required        : >={min_version}\n"
                        f"  Status          : PASS"
                    )
                else:
                    self.errors.append(
                        f"{package} version {version} (normalized: {normalized}) < {min_version} (required)"
                    )
                    self.checks[check_name] = {
                        "status": "error",
                        "version": version,
                        "normalized": normalized,
                        "required": f">={min_version}",
                    }
                    
            except ImportError as e:
                self.errors.append(f"{package} not installed (required): {e}")
                self.checks[check_name] = {
                    "status": "error",
                    "error": str(e),
                }
        
        # Check optional packages
        for package, min_version in optional_packages.items():
            check_name = f"package:{package}"
            try:
                module = __import__(package)
                version = getattr(module, "__version__", "unknown")
                
                # Check version using semantic versioning
                version_ok = _compare_versions(version, min_version)
                normalized = clean_version(version)
                
                if version_ok:
                    self.checks[check_name] = {
                        "status": "ok",
                        "version": version,
                        "normalized": normalized,
                        "required": f">={min_version} (optional)",
                    }
                    logger.info(
                        f"Installed {package} : {version}\n"
                        f"  Normalized      : {normalized}\n"
                        f"  Required        : >={min_version} (optional)\n"
                        f"  Status          : PASS"
                    )
                else:
                    self.warnings.append(
                        f"{package} version {version} (normalized: {normalized}) < {min_version} (optional, but recommended)"
                    )
                    self.checks[check_name] = {
                        "status": "warning",
                        "version": version,
                        "normalized": normalized,
                        "required": f">={min_version} (optional)",
                    }
                    
            except ImportError as e:
                self.warnings.append(f"{package} not installed (optional): {e}")
                self.checks[check_name] = {
                    "status": "warning",
                    "error": str(e),
                }
    
    def _check_model(self, check_name: str, full_path: Path, loader_name: str = "") -> None:
        """Validate a single model — GGUF files vs Transformers directories.

        Args:
            check_name: Check identifier (e.g. "model:generator")
            full_path: Resolved path to model file or directory
            loader_name: Loader class name from model policy (e.g. "LocalGGUFModelLoader")
        """
        is_gguf = (
            loader_name == "LocalGGUFModelLoader"
            or full_path.suffix == ".gguf"
        )

        if is_gguf:
            if full_path.is_file():
                self.checks[check_name] = {
                    "status": "ok",
                    "path": str(full_path),
                    "format": "gguf",
                }
                logger.debug(f"  ✓ {check_name} (GGUF): {full_path.name}")
            else:
                self.errors.append(f"GGUF model file not found: {full_path}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(full_path),
                    "error": "GGUF file not found",
                }
        else:
            if not full_path.exists():
                self.errors.append(f"Model directory not found: {full_path}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(full_path),
                    "error": "Directory not found",
                }
                return

            missing = []
            for required in ("config.json", "tokenizer.json"):
                if not (full_path / required).exists():
                    missing.append(required)

            if missing:
                self.errors.append(f"Model files missing in {full_path}: {', '.join(missing)}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(full_path),
                    "error": f"Missing: {', '.join(missing)}",
                }
                return

            has_weights = (
                (full_path / "pytorch_model.bin").exists() or
                (full_path / "model.safetensors").exists() or
                any(full_path.glob("*.bin")) or
                any(full_path.glob("*.safetensors"))
            )
            if has_weights:
                self.checks[check_name] = {
                    "status": "ok",
                    "path": str(full_path),
                    "files_found": ["config.json", "tokenizer.json", "weights"],
                }
                logger.debug(f"  ✓ {check_name} (Transformers): {full_path}")
            else:
                self.errors.append(f"Model weights not found: {full_path}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(full_path),
                    "error": "No model weights found",
                }

    async def _check_model_files(self) -> None:
        """Check that all required model files exist."""
        logger.debug("Checking model files...")

        ai_models_root = Path(_settings.AI_MODELS)

        # Check every allowed model individually (no dedup by type).
        # This catches both 3B and 0.5B generator GGUF files, embeddings, etc.
        seen_paths: set[str] = set()
        for (model_type, model_name), model in ALLOWED_MODELS.items():
            check_name = f"model:{model_type}:{model_name}"
            full_path = ai_models_root / model.local_subpath
            path_str = str(full_path.resolve())
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)
            self._check_model(check_name, full_path, model.loader_name)
    
    async def _check_gpu(self) -> None:
        """Check GPU availability (optional)."""
        logger.debug("Checking GPU...")
        
        check_name = "gpu:availability"
        
        try:
            import torch
            
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "unknown"
                memory_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3 if gpu_count > 0 else 0
                
                self.checks[check_name] = {
                    "status": "ok",
                    "available": True,
                    "count": gpu_count,
                    "name": gpu_name,
                    "memory_gb": round(memory_gb, 1),
                }
                logger.debug(f"  ✓ GPU: {gpu_name} ({memory_gb:.1f}GB)")
            else:
                self.checks[check_name] = {
                    "status": "warning",
                    "available": False,
                    "message": "CUDA not available, using CPU (slow)",
                }
                self.warnings.append("CUDA not available, using CPU (inference will be 10-30x slower)")
                logger.warning("  ⚠ GPU not available, using CPU")
                
        except ImportError:
            self.checks[check_name] = {
                "status": "warning",
                "available": False,
                "error": "torch not installed",
            }
            self.warnings.append("Cannot check GPU: torch not installed")
    
    async def _check_manifest(self) -> None:
        """Check manifest.json exists and is valid."""
        logger.debug("Checking manifest...")
        
        check_name = "manifest"
        ai_models_root = Path(_settings.AI_MODELS)
        manifest_path = ai_models_root / "manifest.json"
        
        if not manifest_path.exists():
            self.errors.append(f"Manifest not found: {manifest_path}")
            self.checks[check_name] = {
                "status": "error",
                "path": str(manifest_path),
                "error": "File not found",
            }
        else:
            try:
                import json
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                
                # Check required fields
                if "models" not in manifest:
                    self.errors.append("Manifest missing 'models' field")
                    self.checks[check_name] = {
                        "status": "error",
                        "error": "Invalid manifest structure",
                    }
                else:
                    model_count = len(manifest.get("models", {}))
                    self.checks[check_name] = {
                        "status": "ok",
                        "path": str(manifest_path),
                        "models_registered": model_count,
                    }
                    logger.debug(f"  ✓ Manifest: {model_count} models registered")
                    
            except json.JSONDecodeError as e:
                self.errors.append(f"Manifest JSON invalid: {e}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(manifest_path),
                    "error": f"JSON parse error: {e}",
                }
            except Exception as e:
                self.errors.append(f"Manifest read failed: {e}")
                self.checks[check_name] = {
                    "status": "error",
                    "path": str(manifest_path),
                    "error": str(e),
                }
    
    def _build_report(self) -> DependencyReport:
        """Build validation report with consistent structure.
        
        Returns:
            DependencyReport with:
            - checks: Dict of check results
            - warnings: List of warning strings
            - errors: List of error strings
            - summary: Dict with counts
        """
        total_checks = len(self.checks)
        ok_checks = sum(1 for c in self.checks.values() if c.get("status") == "ok")
        error_checks = sum(1 for c in self.checks.values() if c.get("status") == "error")
        warning_checks = sum(1 for c in self.checks.values() if c.get("status") == "warning")
        
        return {
            "checks": self.checks,
            "warnings": self.warnings,  # List[str]
            "errors": self.errors,  # List[str]
            "summary": {
                "total_checks": total_checks,
                "passed": ok_checks,
                "failed": error_checks,
                "warning_count": warning_checks,
                "error_count": len(self.errors),
            }
        }
    
    def get_summary(self) -> str:
        """Get human-readable summary.
        
        Returns:
            Summary string
        """
        if self.errors:
            return f"❌ FAILED: {len(self.errors)} critical errors"
        elif self.warnings:
            return f"⚠️  PASSED with {len(self.warnings)} warnings"
        else:
            return f"✅ PASSED: all checks successful"


# Singleton
_validator = None


def get_dependency_validator() -> DependencyValidator:
    """Get or create dependency validator.
    
    Returns:
        DependencyValidator instance
    """
    global _validator
    if _validator is None:
        _validator = DependencyValidator()
    return _validator


async def validate_dependencies() -> DependencyReport:
    """Validate all AI dependencies.
    
    Returns:
        DependencyReport with checks, warnings, errors, and summary
        
    Raises:
        RuntimeError: If critical dependencies missing
    """
    validator = get_dependency_validator()
    return await validator.validate_all()