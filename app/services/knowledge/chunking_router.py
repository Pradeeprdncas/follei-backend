"""Structure-aware chunking router from the ingestion/storage contract.

The router chooses a deterministic strategy from parsed document structure,
then normalizes every strategy into one metadata envelope shared by
PostgreSQL, FerretDB, and Qdrant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.services.rag.chunking.detectors import looks_like_table
from app.services.rag.chunking.hierarchy import _is_heading
from app.services.rag.chunking.layout import LayoutAwareChunker
from app.services.rag.chunking.semantic import semantic_chunk
from app.services.rag.chunking.table_aware import TableAwareChunker
from app.services.rag.chunking.turn_aware import TurnAwareChunker


@dataclass(frozen=True)
class ChunkingResult:
    strategy: str
    chunks: list[dict]


_MARKDOWN_HEADING = re.compile(r"(?m)^#{1,6}\s+\S+")
_FAQ_QUESTION = re.compile(r"^(?:q(?:uestion)?\s*[:.)-]\s*)?(.+\?)\s*$", re.I)
_FAQ_ANSWER = re.compile(r"^(?:a(?:nswer)?\s*[:.)-]\s*)?(.*)$", re.I)


def _faq_pairs(pages: list[dict]) -> list[dict]:
    pairs: list[dict] = []
    for page in pages:
        explicit = page.get("faqs") or []
        for item in explicit:
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if question and answer:
                pairs.append({"question": question, "answer": answer, "page": page.get("page", 0)})
        lines = [line.strip() for line in str(page.get("text") or "").splitlines() if line.strip()]
        index = 0
        while index < len(lines):
            match = _FAQ_QUESTION.match(lines[index])
            if not match:
                index += 1
                continue
            question = match.group(1).strip()
            index += 1
            answer_lines: list[str] = []
            while index < len(lines) and not _FAQ_QUESTION.match(lines[index]):
                answer = _FAQ_ANSWER.match(lines[index])
                value = (answer.group(1) if answer else lines[index]).strip()
                if value:
                    answer_lines.append(value)
                index += 1
            if answer_lines:
                pairs.append({"question": question, "answer": "\n".join(answer_lines), "page": page.get("page", 0)})
    # Explicit parser pairs and textual pairs can overlap; keep the first.
    unique: dict[str, dict] = {}
    for pair in pairs:
        unique.setdefault(pair["question"].casefold(), pair)
    return list(unique.values())


def _has_heading_structure(pages: list[dict]) -> bool:
    return any(
        page.get("heading")
        or _MARKDOWN_HEADING.search(str(page.get("text") or ""))
        or any(_is_heading(line) for line in str(page.get("text") or "").splitlines())
        for page in pages
    )


def detect_strategy(file_path: str | Path, pages: list[dict], *, metadata: dict | None = None) -> str:
    path = Path(file_path)
    metadata = metadata or {}
    explicit = str(metadata.get("chunking_strategy") or "").strip().lower()
    if explicit in {"layout_aware", "table_preserving", "semantic", "faq_pair", "slide", "turn_aware"}:
        return explicit
    source_type = str(metadata.get("source_type") or path.suffix.lstrip(".")).lower()
    category = str(metadata.get("category") or "").lower()
    text = "\n".join(str(page.get("text") or "") for page in pages)
    if source_type in {"ppt", "pptx"} or any(page.get("structure") == "slide" for page in pages):
        return "slide"
    if category in {"faq", "faqs"} or _faq_pairs(pages):
        return "faq_pair"
    if source_type in {"csv", "xlsx"} or looks_like_table(text):
        return "table_preserving"
    if any(token in f"{source_type} {path.name.lower()}" for token in ("email", "eml", "msg", "call", "transcript", "voice")):
        return "turn_aware"
    if _has_heading_structure(pages):
        return "layout_aware"
    return "semantic"


def _semantic_chunks(pages: list[dict]) -> list[dict]:
    result: list[dict] = []
    for page in pages:
        for value in semantic_chunk(str(page.get("text") or "")):
            if value.strip():
                result.append({
                    "chunk_id": str(uuid4()), "text": value.strip(), "page": page.get("page", 0),
                    "heading": page.get("heading"), "section_path": [page["heading"]] if page.get("heading") else [],
                    "chunk_type": "prose",
                })
    return result


def _faq_chunks(pages: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": str(uuid4()), "text": f"{pair['question']}\n{pair['answer']}",
            "page": pair["page"], "heading": pair["question"],
            "section_path": ["FAQs", pair["question"]], "chunk_type": "faq",
        }
        for pair in _faq_pairs(pages)
    ]


def _slide_chunks(pages: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": str(uuid4()), "text": str(page.get("text") or "").strip(),
            "page": page.get("page", 0), "heading": page.get("heading") or f"Slide {page.get('page', 0)}",
            "section_path": [page.get("heading") or f"Slide {page.get('page', 0)}"], "chunk_type": "slide",
        }
        for page in pages if str(page.get("text") or "").strip()
    ]


def route_chunks(file_path: str | Path, pages: list[dict], *, metadata: dict | None = None) -> ChunkingResult:
    metadata = dict(metadata or {})
    strategy = detect_strategy(file_path, pages, metadata=metadata)
    if strategy == "table_preserving":
        chunks = TableAwareChunker().chunk(pages, metadata=metadata)
    elif strategy == "layout_aware":
        chunks = LayoutAwareChunker().chunk(pages, metadata=metadata)
    elif strategy == "turn_aware":
        chunks = TurnAwareChunker().chunk(pages, metadata=metadata)
    elif strategy == "faq_pair":
        chunks = _faq_chunks(pages)
    elif strategy == "slide":
        chunks = _slide_chunks(pages)
    else:
        chunks = _semantic_chunks(pages)

    previous_id: str | None = None
    for index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id") or uuid4())
        heading_path = [str(value) for value in (chunk.get("heading_path") or chunk.get("section_path") or []) if value]
        canonical_type = {
            "table_row": "table", "paragraph": "prose", "code": "prose",
            "list": "prose", "speaker_turn": "prose",
        }.get(str(chunk.get("chunk_type") or "prose"), str(chunk.get("chunk_type") or "prose"))
        content = str(chunk.get("text") or "").strip()
        chunk.update({
            "chunk_id": chunk_id,
            "chunk_index": index,
            "source_id": str(metadata.get("source_id") or ""),
            "tenant_id": str(metadata.get("tenant_id") or ""),
            "category": str(metadata.get("category") or "general"),
            "heading_path": heading_path,
            "section_path": heading_path,
            "page_number": int(chunk.get("page") or 0),
            "chunk_type": canonical_type,
            "token_count": max(1, len(content.split())),
            "word_count": len(content.split()),
            "text": content,
            "chunking_strategy": strategy,
            "prev_chunk_id": previous_id,
            "next_chunk_id": None,
            "approval_status": chunk.get("approval_status") or "draft",
            "sensitivity": chunk.get("sensitivity") or metadata.get("sensitivity", "internal"),
            "source_type": chunk.get("source_type") or metadata.get("source_type", "document"),
        })
        if index:
            chunks[index - 1]["next_chunk_id"] = chunk_id
        previous_id = chunk_id
    return ChunkingResult(strategy=strategy, chunks=chunks)
