"""Live regression coverage for bootstrapping an empty PostgreSQL database."""
from __future__ import annotations

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.config.settings import get_settings
from app.database.base import Base
import app.models  # noqa: F401 - load the schema Alembic must create


@pytest.mark.integration
def test_empty_postgres_reaches_head_using_alembic_upgrade_only(monkeypatch):
    root_url = make_url(get_settings().DATABASE_URL)
    database_name = f"follei_bootstrap_{uuid4().hex[:12]}"
    admin_engine = create_engine(root_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    database_url = root_url.set(database=database_name)

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert inspect(connection).get_table_names() == []

        monkeypatch.setenv(
            "ALEMBIC_DATABASE_URL",
            database_url.render_as_string(hide_password=False),
        )
        config = Config("alembic.ini")
        command.upgrade(config, "head")

        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        missing_tables = set(Base.metadata.tables) - tables
        assert missing_tables == set(), f"Alembic omitted registered tables: {sorted(missing_tables)}"
        assert len(tables) == len(Base.metadata.tables) + 1
        assert revision == "20260813_passwordless_otp"

        command.check(config)
        command.downgrade(config, "base")
        with engine.connect() as connection:
            remaining = set(inspect(connection).get_table_names()) - {"alembic_version"}
        assert remaining == set()
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()
