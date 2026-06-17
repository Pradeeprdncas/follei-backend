from app.services.rag.chunking.detectors import (
    looks_like_table,
    looks_like_code,
    looks_like_list,
)

from app.services.rag.chunking.semantic import semantic_chunk


def adaptive_chunk(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
):

    if looks_like_table(text):
        return [{
            "chunk_type": "table",
            "text": text,
        }]

    if looks_like_code(text):
        return [{
            "chunk_type": "code",
            "text": text,
        }]

    if looks_like_list(text):
        return [{
            "chunk_type": "list",
            "text": text,
        }]

    chunks = semantic_chunk(
        text=text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return [
        {
            "chunk_type": "paragraph",
            "text": chunk,
        }
        for chunk in chunks
    ]