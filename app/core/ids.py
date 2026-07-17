"""Short ID generation for in-memory entity references."""
import uuid


def short_id() -> str:
    """Generate a compact, URL-safe unique identifier."""
    return uuid.uuid4().hex[:12]
