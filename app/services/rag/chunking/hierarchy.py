from uuid import uuid4
import re
from app.services.rag.chunking.adaptive import adaptive_chunk


_HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)")


def _is_heading(line: str) -> bool:
    """Conservative heading detector for parsers that only return plain text.

    PDF/DOCX parsers do not always expose layout headings.  Short standalone
    title-case or uppercase lines are still valuable structure, but sentences,
    table rows and list items must remain content.
    """
    value = line.strip()
    if re.match(r"^#{1,6}\s+\S+", value):
        return True
    words = value.split()
    if not value or len(words) > 12 or value.endswith((".", ";", ":", "?", "!")):
        return False
    if "|" in value or "," in value or value.startswith(("-", "*", "•")):
        return False
    stripped = _HEADING_NUMBER.sub("", value).lstrip("#").strip()
    if len(stripped) < 3:
        return False
    return stripped.isupper() or (len(words) >= 2 and stripped.istitle())


def _sections(page: dict) -> list[tuple[str | None, str]]:
    """Return heading/text sections while respecting an explicit parser heading."""
    explicit_heading = page.get("heading")
    lines = str(page.get("text", "")).splitlines()
    result: list[tuple[str | None, str]] = []
    heading = explicit_heading
    body: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if _is_heading(line):
            if body:
                result.append((heading, "\n".join(body).strip()))
                body = []
            heading = line.lstrip("#").strip()
        elif line:
            body.append(raw_line)
    if body:
        result.append((heading, "\n".join(body).strip()))
    return result or [(explicit_heading, str(page.get("text", "")))]


def hierarchy_chunk(pages):

    chunks = []

    previous_chunk = None

    for page in pages:

        page_number = page["page"]

        for heading, text in _sections(page):
            if not text:
                continue
            adaptive_chunks = adaptive_chunk(text)
            parent_id = str(uuid4())
            for idx, chunk in enumerate(adaptive_chunks):

                chunk_id = str(uuid4())

                chunks.append({
                    "chunk_id": chunk_id,
                    "parent_chunk_id": parent_id,
                    "prev_chunk_id": previous_chunk,
                    "next_chunk_id": None,

                    "page": page_number,

                    "heading": heading,

                    "section_path": [heading] if heading else [],

                    "chunk_index": idx,

                    "chunk_type": chunk["chunk_type"],

                    "word_count": len(chunk["text"].split()),

                    "text": chunk["text"]
                })

                if len(chunks) > 1:
                    chunks[-2]["next_chunk_id"] = chunk_id

                previous_chunk = chunk_id

    return chunks
