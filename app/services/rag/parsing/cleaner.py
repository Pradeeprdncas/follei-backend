"""Text cleaning utilities."""
import re
from loguru import logger


def clean_text(text: str) -> str:
    """
    Clean raw extracted text:
    - Collapse multiple whitespace
    - Remove control chars
    - Strip leading/trailing whitespace
    - Remove repeated newlines
    """
    if not text:
        return ""
    
    # FIX: Using safe python escape codes (\x00-\x08, \x0b-\x0c, \x0e-\x1f, \x7f) 
    # instead of embedding literal binary control characters.
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    
    # Collapse multiple whitespace to single space
    text = re.sub(r'[ ]+', ' ', text)
    
    # Collapse multiple newlines to double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip per line and rejoin
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


def remove_headers_footers(text: str, common_patterns: list[str] | None = None) -> str:
    """Remove common header/footer patterns (page numbers, etc.)."""
    patterns = common_patterns or [
        r'^\s*Page\s+\d+\s+of\s+\d+\s*$',
        r'^\s*\d+\s*$',
        r'^\s*Confidential\s*$',
    ]
    lines = text.split('\n')
    filtered = []
    for line in lines:
        skip = False
        for pat in patterns:
            if re.match(pat, line, re.IGNORECASE):
                skip = True
                break
        if not skip:
            filtered.append(line)
    return '\n'.join(filtered)