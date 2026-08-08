"""Validate immutable Alembic sources and recover corrupted tracked files."""
from __future__ import annotations

import ast
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "current_versions"
BACKUPS = ROOT / "logs" / "migration-repairs"


class MigrationSourceError(RuntimeError):
    pass


def _metadata(source: bytes, path: Path) -> tuple[str, str | None]:
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeError) as exc:
        raise MigrationSourceError(f"invalid Python in {path.name}: {exc}") from exc
    values: dict[str, str | None] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            if value is None or isinstance(value, str):
                values[target.id] = value
    revision = values.get("revision")
    if not revision:
        raise MigrationSourceError(f"{path.name} does not declare a string revision")
    return revision, values.get("down_revision")


def _git_source(path: Path, root: Path) -> bytes:
    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        raise MigrationSourceError("Git checkout is unavailable for automatic repair")
    relative = path.relative_to(root).as_posix()
    result = subprocess.run(
        [git, "show", f"HEAD:{relative}"],
        cwd=root,
        capture_output=True,
        timeout=15,
    )
    if result.returncode or not result.stdout:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise MigrationSourceError(f"Git could not restore {relative}: {detail}")
    _metadata(result.stdout, path)
    return result.stdout


def _repair(path: Path, *, root: Path, backup_directory: Path) -> None:
    canonical = _git_source(path, root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup = backup_directory / f"{path.name}.{timestamp}.corrupt"
    backup.write_bytes(path.read_bytes())
    temporary = path.with_suffix(path.suffix + ".repairing")
    temporary.write_bytes(canonical)
    temporary.replace(path)


def validate_migration_sources(
    *,
    versions: Path = VERSIONS,
    root: Path = ROOT,
    backup_directory: Path = BACKUPS,
    repair: bool = True,
) -> list[str]:
    """Return repaired filenames, or fail before Alembic touches the database."""
    repaired: list[str] = []
    metadata: dict[str, tuple[str | None, Path]] = {}
    for path in sorted(versions.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            revision, down_revision = _metadata(path.read_bytes(), path)
        except (MigrationSourceError, OSError) as exc:
            if not repair:
                raise
            try:
                _repair(path, root=root, backup_directory=backup_directory)
                revision, down_revision = _metadata(path.read_bytes(), path)
            except Exception as repair_exc:
                raise MigrationSourceError(
                    f"Alembic migration {path.name} is corrupted and could not be repaired. "
                    f"Run `git restore -- {path.relative_to(root).as_posix()}`. Original error: {exc}. "
                    f"Repair error: {repair_exc}"
                ) from repair_exc
            repaired.append(path.name)
        if revision in metadata:
            raise MigrationSourceError(f"duplicate Alembic revision {revision!r}")
        metadata[revision] = (down_revision, path)

    revisions = set(metadata)
    referenced = {down for down, _ in metadata.values() if down}
    missing = sorted(referenced - revisions)
    if missing:
        raise MigrationSourceError(f"Alembic chain references missing revisions: {missing}")
    heads = sorted(revisions - referenced)
    if len(heads) != 1:
        raise MigrationSourceError(f"Alembic must have exactly one head; found {heads}")
    return repaired
