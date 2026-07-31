"""Make the Compose PostgreSQL role match Follei's local DATABASE_URL.

PostgreSQL only applies POSTGRES_* variables when its data directory is first
created. This repairs an older local volume whose original Compose credentials
differ from the current .env, without deleting the volume or application data.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg2


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
PROJECT = "follei-backend-team"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _can_connect(database_url: str) -> bool:
    try:
        connection = psycopg2.connect(database_url, connect_timeout=3)
        connection.close()
        return True
    except psycopg2.OperationalError:
        return False


def _is_superuser(database_url: str) -> bool:
    try:
        connection = psycopg2.connect(database_url, connect_timeout=3)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            )
            result = cursor.fetchone()
        connection.close()
        return bool(result and result[0])
    except psycopg2.OperationalError:
        return False


def _docker(
    *arguments: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=20,
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_identifier(value: str) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise RuntimeError(
            f"unsafe PostgreSQL identifier in local configuration: {value!r}"
        )
    return '"' + value.replace('"', '""') + '"'


def ensure_access() -> str:
    values = _load_env()
    database_url = values.get("DATABASE_URL", "")
    parsed = urlsplit(database_url)
    app_user = unquote(parsed.username or "")
    app_password = unquote(parsed.password or "")
    app_database = parsed.path.lstrip("/")

    if not app_user or not app_password or not app_database:
        raise RuntimeError(
            "DATABASE_URL must include a username, password, and database"
        )
    if parsed.hostname not in {"127.0.0.1", "localhost"} or (
        parsed.port or 5432
    ) != 55589:
        if _can_connect(database_url):
            return "external-connected"
        raise RuntimeError(
            "DATABASE_URL is not the local Compose PostgreSQL database and is unreachable"
        )
    if _can_connect(database_url) and _is_superuser(database_url):
        return "connected"

    container_result = _docker(
        "compose",
        "-p",
        PROJECT,
        "-f",
        str(COMPOSE),
        "ps",
        "-q",
        "postgres",
    )
    container = container_result.stdout.strip()
    if container_result.returncode or not container:
        raise RuntimeError("local PostgreSQL container was not found")

    inspect_result = _docker(
        "inspect",
        "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
        container,
    )
    if inspect_result.returncode:
        raise RuntimeError("could not inspect the local PostgreSQL container")
    container_env = dict(
        line.split("=", 1)
        for line in inspect_result.stdout.splitlines()
        if "=" in line
    )
    configured_admin = container_env.get("POSTGRES_USER", "")
    admin_database = container_env.get("POSTGRES_DB", "")
    _sql_identifier(admin_database)

    # A recreated container can show new POSTGRES_* values while retaining an
    # older data directory. Probe likely local roles through PostgreSQL's Unix
    # socket and select the actual superuser that owns that directory.
    candidates = dict.fromkeys(
        candidate
        for candidate in (configured_admin, app_user, "username", "postgres")
        if candidate and SAFE_IDENTIFIER.fullmatch(candidate)
    )
    admin_user = ""
    for candidate in candidates:
        probe = _docker(
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            candidate,
            "-d",
            admin_database,
            "-tAc",
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user",
        )
        if probe.returncode == 0 and probe.stdout.strip() == "t":
            admin_user = candidate
            break
    if not admin_user:
        raise RuntimeError("could not locate the local PostgreSQL superuser")

    role = _sql_identifier(app_user)
    database = _sql_identifier(app_database)
    user_literal = _sql_literal(app_user)
    password_literal = _sql_literal(app_password)
    sql = f"""
DO $follei$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {user_literal}) THEN
    EXECUTE 'ALTER ROLE ' || quote_ident({user_literal}) ||
            ' WITH LOGIN SUPERUSER PASSWORD ' || quote_literal({password_literal});
  ELSE
    EXECUTE 'CREATE ROLE ' || quote_ident({user_literal}) ||
            ' WITH LOGIN SUPERUSER PASSWORD ' || quote_literal({password_literal});
  END IF;
END
$follei$;
GRANT ALL PRIVILEGES ON DATABASE {database} TO {role};
GRANT ALL PRIVILEGES ON SCHEMA public TO {role};
"""
    repair_result = _docker(
        "exec",
        "-i",
        container,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        admin_user,
        "-d",
        admin_database,
        input_text=sql,
    )
    if repair_result.returncode:
        raise RuntimeError(
            "could not reconcile the local PostgreSQL role: "
            + repair_result.stderr.strip()
        )
    if not _can_connect(database_url):
        raise RuntimeError(
            "PostgreSQL role was repaired but DATABASE_URL still cannot connect"
        )
    return "repaired"


if __name__ == "__main__":
    try:
        print(f"postgres_access={ensure_access()}")
    except Exception as exc:
        print(f"postgres_access=failed error={exc}", file=sys.stderr)
        raise SystemExit(1)
