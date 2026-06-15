"""Semantic chunking using RecursiveCharacterTextSplitter."""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def semantic_chunk(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[str]:
    """
    Split text into semantic chunks.
    Returns list of chunk strings.
    """
    size = chunk_size or _settings.CHUNK_SIZE
    overlap = chunk_overlap or _settings.CHUNK_OVERLAP

    # FIX: Explicitly using string literal escape codes ("\n\n", "\n") 
    # instead of embedding raw structural line breaks.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)
    logger.info(f"Semantic chunk: {len(text)} chars → {len(chunks)} chunks")
    return chunks