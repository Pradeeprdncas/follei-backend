"""Stable human-readable public identifiers for operational records."""
import secrets


def generate_public_id(kind: str) -> str:
    prefix = "".join(ch for ch in kind.upper() if ch.isalnum())[:8] or "OBJ"
    return f"{prefix}_{secrets.token_urlsafe(8)}"
