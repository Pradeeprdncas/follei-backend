"""Rotate Follei's local-only credentials without printing secret values.

This deliberately does not touch provider credentials (Mistral, Brevo,
Google, Meta, Hugging Face, ElevenLabs). Those must be revoked and recreated
in their provider control planes.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
COMPOSE_PATH = ROOT / "docker-compose.yml"


def _load_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _replace_env(text: str, replacements: dict[str, str]) -> str:
    remaining = dict(replacements)
    output: list[str] = []
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if remaining:
        output.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(output) + "\n"


def _replace_compose_credentials(text: str) -> str:
    service = ""
    output: list[str] = []
    replacements = {
        ("minio", "MINIO_ROOT_USER"): "${OBJECT_STORAGE_ACCESS_KEY}",
        ("minio", "MINIO_ROOT_PASSWORD"): "${OBJECT_STORAGE_SECRET_KEY}",
        ("ferretdb-postgres", "POSTGRES_USER"): "${FERRETDB_USER}",
        ("ferretdb-postgres", "POSTGRES_PASSWORD"): "${FERRETDB_PASSWORD}",
        (
            "ferretdb",
            "FERRETDB_POSTGRESQL_URL",
        ): "postgres://${FERRETDB_USER}:${FERRETDB_PASSWORD}@ferretdb-postgres:5432/postgres",
    }
    for line in text.splitlines():
        service_match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
        if service_match:
            service = service_match.group(1)
        key_match = re.match(r"^(\s+)([A-Z][A-Z0-9_]+):\s*.*$", line)
        if key_match and (service, key_match.group(2)) in replacements:
            line = f"{key_match.group(1)}{key_match.group(2)}: {replacements[(service, key_match.group(2))]}"
        output.append(line)
    return "\n".join(output) + "\n"


def _run_sql(container: str, user: str, database: str, sql: str) -> None:
    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database],
        input=sql,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"credential rotation failed for {container}: {result.stderr.strip()}")


def _role_from_database_url(value: str) -> str:
    role = urlsplit(value).username
    if not role or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", role):
        raise RuntimeError("DATABASE_URL contains an invalid role")
    return role


def main() -> int:
    if not ENV_PATH.exists() or not COMPOSE_PATH.exists():
        raise RuntimeError("run from a complete Follei workspace containing .env and docker-compose.yml")

    env_text = ENV_PATH.read_text(encoding="utf-8")
    values = _load_env(env_text)
    database_url = values.get("DATABASE_URL", "")
    database_role = _role_from_database_url(database_url)

    main_password = secrets.token_urlsafe(32)
    ferret_password = secrets.token_urlsafe(32)
    minio_access = "follei" + secrets.token_hex(8)
    minio_secret = secrets.token_urlsafe(40)
    jwt_secret = secrets.token_urlsafe(48)

    database = urlsplit(database_url)
    new_database_url = (
        f"{database.scheme}://{database_role}:{quote(main_password, safe='')}@"
        f"{database.hostname}:{database.port or 5432}{database.path}"
    )
    ferret_database = values.get("FERRETDB_DATABASE", "follei_knowledge")
    new_ferret_url = (
        f"mongodb://follei:{quote(ferret_password, safe='')}@127.0.0.1:27017/"
        f"{ferret_database}?authSource=postgres"
    )

    replacements = {
        "POSTGRES_USER": database_role,
        "POSTGRES_PASSWORD": main_password,
        "POSTGRES_DB": database.path.lstrip("/"),
        "DATABASE_URL": new_database_url,
        "FERRETDB_USER": "follei",
        "FERRETDB_PASSWORD": ferret_password,
        "FERRETDB_URL": new_ferret_url,
        "SECRET_KEY": jwt_secret,
        "OBJECT_STORAGE_ACCESS_KEY": minio_access,
        "OBJECT_STORAGE_SECRET_KEY": minio_secret,
    }

    # The running main database was initialized with a different superuser;
    # alter only the application's role and do not recreate this container.
    _run_sql(
        "follei-backend-team-postgres-1",
        "username",
        "follei_main",
        f'ALTER ROLE "{database_role}" WITH PASSWORD \'{main_password}\';\n',
    )
    _run_sql(
        "follei-backend-team-ferretdb-postgres-1",
        "follei",
        "postgres",
        f"ALTER ROLE follei WITH PASSWORD '{ferret_password}';\n",
    )

    new_env_text = _replace_env(env_text, replacements)
    new_compose_text = _replace_compose_credentials(COMPOSE_PATH.read_text(encoding="utf-8"))
    ENV_PATH.write_text(new_env_text, encoding="utf-8", newline="\n")
    COMPOSE_PATH.write_text(new_compose_text, encoding="utf-8", newline="\n")

    process_env = os.environ.copy()
    process_env.update(replacements)
    for service in ("minio", "ferretdb"):
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", service],
            cwd=ROOT,
            env=process_env,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(f"failed to restart {service}: {result.stderr.strip()}")

    print("LOCAL_ROTATION=complete")
    print("ROTATED=postgres,ferretdb,minio,jwt")
    print("SECRET_VALUES_PRINTED=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LOCAL_ROTATION=failed TYPE={type(exc).__name__} ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
