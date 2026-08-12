"""Structured JSON extraction for connector-produced knowledge sources."""
from __future__ import annotations

import json
from pathlib import Path


_BINARY_CONTENT_FIELDS = {"content_base64", "data", "raw"}
# Aggregate connector documents are the review/search projection, while the
# complete source record remains in object storage. Cap one record here so a
# single huge Sheet/Doc cannot multiply into hundreds of chunks and exhaust a
# worker. Dedicated binary/native-file ingestion can later parse the original.
MAX_STRUCTURED_RECORD_CHARS = 6_000


def _knowledge_record(record: object) -> object:
    """Return connector data that is useful for search, without binary blobs.

    Google Drive and Gmail preserve binary payloads in object storage for later
    dedicated-file processing.  Serializing those blobs into the aggregate JSON
    document creates enormous, meaningless chunks and can exhaust the embedding
    provider.  Native Google documents already expose ``content_text`` and keep
    that text here; binary files retain their metadata and sync status.
    """
    if isinstance(record, list):
        return [_knowledge_record(item) for item in record]
    if not isinstance(record, dict):
        return record

    cleaned: dict[str, object] = {}
    for key, value in record.items():
        if key in _BINARY_CONTENT_FIELDS:
            continue
        if key == "body_html" and record.get("body_text"):
            continue
        if key == "attachments" and isinstance(value, list):
            cleaned[key] = [
                _knowledge_record({
                    field: attachment.get(field)
                    for field in ("attachment_id", "filename", "mime_type", "content_size")
                    if attachment.get(field) is not None
                })
                for attachment in value
                if isinstance(attachment, dict)
            ]
            continue
        cleaned[key] = _knowledge_record(value)
    return cleaned


def extract_json_text(file_path: str | Path) -> list[dict]:
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    resource = payload.get("resource") if isinstance(payload, dict) else None
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        records = [records]
    pages: list[dict] = []
    for index, record in enumerate(records):
        if record is None:
            continue
        text = json.dumps(_knowledge_record(record), ensure_ascii=False, default=str)
        if text and text != "{}":
            pages.append({
                "page": len(pages),
                "text": text[:MAX_STRUCTURED_RECORD_CHARS],
                "heading": f"{resource or 'record'} {index + 1}",
                "structure": "structured_record",
            })
    return pages
