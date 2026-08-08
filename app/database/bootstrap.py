"""Prepare local databases exclusively through the canonical Alembic chain."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.database.base import Base
from app.config.database import engine
import app.models  # noqa: F401 - registers canonical mappings on Base.metadata
from app.database.migration_preflight import validate_migration_sources


ALEMBIC_VERSION_TABLE = "alembic_version"


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    return Config(str(root / "alembic.ini"))


def ensure_base_schema() -> tuple[str, int]:
    """Create a fresh schema or migrate an Alembic-managed one.

    Existing databases that contain Follei tables but have no Alembic revision
    are deliberately rejected.  Stamping such a database automatically could
    hide an incomplete or incompatible schema and risks data loss.
    """
    repaired = validate_migration_sources()
    if repaired:
        print(f"migration_sources_repaired={','.join(repaired)}")
    tables = set(inspect(engine).get_table_names())
    canonical_tables = set(Base.metadata.tables)

    if ALEMBIC_VERSION_TABLE in tables:
        command.upgrade(_alembic_config(), "head")
        return "migrated", len(canonical_tables)

    if tables & canonical_tables:
        raise RuntimeError(
            "Found an existing unversioned Follei schema. Refusing to guess its "
            "Alembic revision. Back up the database, verify it is current, then "
            "run `python -m alembic stamp head` once before starting Follei."
        )

    command.upgrade(_alembic_config(), "head")
    return "initialized", len(canonical_tables)


if __name__ == "__main__":
    action, table_count = ensure_base_schema()
    print(f"schema_status={action} verified_tables={table_count}")
