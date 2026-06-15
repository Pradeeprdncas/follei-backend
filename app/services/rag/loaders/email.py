"""Email text extraction placeholder."""
from pathlib import Path
from loguru import logger


def extract_email_text(file_path: str | Path) -> list[dict]:
    """Placeholder for email extraction — returns empty for now."""
    logger.warning(f"Email extraction not yet implemented for {file_path}")
    return []
