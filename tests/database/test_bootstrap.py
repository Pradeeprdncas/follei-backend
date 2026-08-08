"""Unit tests for local database startup strategy selection."""
from unittest.mock import Mock, patch

import pytest

from app.database import bootstrap


def _inspector(*tables: str) -> Mock:
    inspector = Mock()
    inspector.get_table_names.return_value = list(tables)
    return inspector


@patch("app.database.bootstrap.command.upgrade")
@patch("app.database.bootstrap.inspect")
def test_bootstrap_initializes_empty_database_with_alembic_upgrade_only(
    inspect_mock: Mock, upgrade: Mock
) -> None:
    inspect_mock.return_value = _inspector()

    action, count = bootstrap.ensure_base_schema()

    assert action == "initialized"
    assert count == len(bootstrap.Base.metadata.tables)
    assert upgrade.call_count == 1
    assert upgrade.call_args.args[1] == "head"


@patch("app.database.bootstrap.command.upgrade")
@patch("app.database.bootstrap.inspect")
def test_bootstrap_only_migrates_versioned_database(
    inspect_mock: Mock, upgrade: Mock
) -> None:
    inspect_mock.return_value = _inspector("alembic_version", "tenants")

    action, _ = bootstrap.ensure_base_schema()

    assert action == "migrated"
    assert upgrade.call_count == 1
    assert upgrade.call_args.args[1] == "head"


@patch("app.database.bootstrap.inspect")
def test_bootstrap_rejects_unversioned_existing_schema(inspect_mock: Mock) -> None:
    inspect_mock.return_value = _inspector("tenants")

    with pytest.raises(RuntimeError, match="unversioned Follei schema"):
        bootstrap.ensure_base_schema()
