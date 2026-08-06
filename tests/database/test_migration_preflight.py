from pathlib import Path

import pytest

from app.database import migration_preflight


BASE = b'revision = "base"\ndown_revision = None\n'
HEAD = b'revision = "head"\ndown_revision = "base"\n'


def test_valid_single_head_chain_passes(tmp_path: Path):
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "001_base.py").write_bytes(BASE)
    (versions / "002_head.py").write_bytes(HEAD)

    assert migration_preflight.validate_migration_sources(
        versions=versions, root=tmp_path, backup_directory=tmp_path / "backups", repair=False
    ) == []


def test_corrupt_tracked_migration_is_backed_up_and_restored(tmp_path: Path, monkeypatch):
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    broken = versions / "001_base.py"
    broken.write_text("1` broken migration", encoding="utf-8")
    (versions / "002_head.py").write_bytes(HEAD)
    monkeypatch.setattr(migration_preflight, "_git_source", lambda _path, _root: BASE)
    backups = tmp_path / "backups"

    repaired = migration_preflight.validate_migration_sources(
        versions=versions, root=tmp_path, backup_directory=backups, repair=True
    )

    assert repaired == ["001_base.py"]
    assert broken.read_bytes() == BASE
    assert len(list(backups.glob("001_base.py.*.corrupt"))) == 1


def test_corrupt_migration_without_repair_fails_before_alembic(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "broken.py").write_text("not python `", encoding="utf-8")

    with pytest.raises(migration_preflight.MigrationSourceError, match="invalid Python"):
        migration_preflight.validate_migration_sources(
            versions=versions, root=tmp_path, backup_directory=tmp_path / "backups", repair=False
        )
