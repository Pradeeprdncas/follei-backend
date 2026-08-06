"""Tests for portable local PostgreSQL credential reconciliation."""
from unittest.mock import Mock, patch

import pytest

from scripts import ensure_local_postgres_access as access


DATABASE_URL = "postgresql://follei:secret@127.0.0.1:55589/follei_main"


@patch.object(access, "_docker")
@patch.object(access, "_is_superuser", return_value=True)
@patch.object(access, "_can_connect", return_value=True)
@patch.object(access, "_load_env", return_value={"DATABASE_URL": DATABASE_URL})
def test_existing_credentials_need_no_docker_changes(
    _load_env: Mock, _can_connect: Mock, _is_superuser: Mock, docker: Mock
) -> None:
    assert access.ensure_access() == "connected"
    docker.assert_not_called()


@patch.object(access, "_can_connect", return_value=False)
@patch.object(
    access,
    "_load_env",
    return_value={"DATABASE_URL": "postgresql://follei:secret@db.example:5432/follei"},
)
def test_unreachable_external_database_is_not_modified(
    _load_env: Mock, _can_connect: Mock
) -> None:
    with pytest.raises(RuntimeError, match="not the local Compose"):
        access.ensure_access()


def test_sql_values_are_quoted() -> None:
    assert access._sql_literal("it's") == "'it''s'"
    assert access._sql_identifier("follei_main") == '"follei_main"'
    with pytest.raises(RuntimeError, match="unsafe PostgreSQL identifier"):
        access._sql_identifier("follei; DROP DATABASE follei")


@patch.object(access, "_is_superuser", return_value=False)
@patch.object(access, "_can_connect", side_effect=[False, True])
@patch.object(access, "_load_env", return_value={"DATABASE_URL": DATABASE_URL})
def test_repair_sets_env_password_superuser_ownership_and_all_privileges(
    _load_env: Mock, _can_connect: Mock, _is_superuser: Mock, monkeypatch
) -> None:
    responses = iter([
        Mock(returncode=0, stdout="container-id\n", stderr=""),
        Mock(returncode=0, stdout="POSTGRES_USER=legacy_admin\nPOSTGRES_DB=follei_main\n", stderr=""),
        Mock(returncode=0, stdout="t\n", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
    ])
    calls = []

    def fake_docker(*args, input_text=None):
        calls.append((args, input_text))
        return next(responses)

    monkeypatch.setattr(access, "_docker", fake_docker)

    assert access.ensure_access() == "repaired"
    role_sql = calls[3][1]
    privilege_sql = calls[4][1]
    assert "WITH LOGIN SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS PASSWORD" in role_sql
    assert 'ALTER DATABASE "follei_main" OWNER TO "follei"' in role_sql
    assert "ALTER SCHEMA public OWNER" in privilege_sql
    assert "ALL TABLES IN SCHEMA public" in privilege_sql
    assert "ALTER DEFAULT PRIVILEGES" in privilege_sql
    assert calls[4][0][-1] == "follei_main"
