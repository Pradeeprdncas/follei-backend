"""Canonical document identity, deduplication, and version-chain helpers."""
from __future__ import annotations
import hashlib
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.knowledge.document import DocumentVersion


def sha256_file(file_path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def next_version(previous_version: int | None) -> int:
    return (previous_version or 0) + 1


def stable_upload_uri(tenant_id: str, filename: str) -> str:
    """Stable source identity for repeated uploads of the same named source."""
    return f"upload://{tenant_id}/{Path(filename).name}"


def reserve_document(
    *, db: Session, tenant_id: str, file_path: str | Path, source_uri: str,
    filename: str, source_type: str, uploaded_by: str | None = None,
) -> tuple[Document, bool]:
    """Return (document, is_duplicate); changed content becomes a linked version."""
    content_hash = sha256_file(file_path)
    duplicate = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id, Document.content_hash == content_hash)
        .first()
    )
    if duplicate:
        return duplicate, True

    previous = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id, Document.source_uri == source_uri)
        .order_by(Document.version.desc(), Document.created_at.desc())
        .first()
    )
    version = next_version(previous.version if previous else None)
    document = Document(
        tenant_id=tenant_id,
        title=filename,
        source_uri=source_uri,
        source_type=source_type,
        path=str(file_path),
        file_size=Path(file_path).stat().st_size,
        content_hash=content_hash,
        version=version,
        previous_document_id=previous.id if previous else None,
        sensitivity="internal",
        uploaded_by=uploaded_by,
        status="processing",
        tags=[],
        keywords=[],
        metadata_={},
    )
    db.add(document)
    db.flush()
    db.add(DocumentVersion(
        tenant_id=tenant_id,
        document_id=document.id,
        version=version,
        title=filename,
        content_hash=content_hash,
        path=str(file_path),
        metadata_={"source_uri": source_uri, "previous_document_id": str(previous.id) if previous else None},
    ))
    db.commit()
    db.refresh(document)
    return document, False

