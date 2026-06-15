"""PPT text extraction placeholder."""
from pathlib import Path
from loguru import logger


def extract_ppt_text(file_path: str | Path) -> list[dict]:
    """Placeholder for PPT extraction — returns empty for now."""
    logger.warning(f"PPT extraction not yet implemented for {file_path}")
    return []
