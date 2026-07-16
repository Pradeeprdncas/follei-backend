from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.models.knowledge.document import Document, DocumentChunk, DocumentPage, KnowledgeSource
from app.models.tenancy import User
from app.routers.auth import get_current_user
from app.schemas.document import (
    DocumentChunkRead,
    DocumentChunkCreateItem,
    DocumentChunkListItem,
    DocumentChunksCreate,
    DocumentChunksCreateResponse,
    DocumentChunksListResponse,
    DocumentCreate,
    DocumentCreateResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentRead,
    DocumentUpdate,
)
from app.services.qdrant import delete_document_vectors

router = APIRouter(prefix="/documents", tags=["Documents"])


def _ensure_tenant(current_user: User, tenant_id: UUID) -> None:
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _get_document_or_404(db: Session, current_user: User, document_id: UUID) -> Document:
    document = (
        db.query(Document)
        .options(selectinload(Document.chunks), selectinload(Document.pages))
        .filter(Document.id == document_id, Document.tenant_id == current_user.tenant_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _validate_source(db: Session, tenant_id: UUID, source_id: Optional[UUID]) -> None:
    if source_id is None:
        return

    source = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.id == source_id, KnowledgeSource.tenant_id == tenant_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")


def _document_response(document: Document) -> DocumentCreateResponse:
    return DocumentCreateResponse(
        id=document.id,
        source_id=document.source_id,
        filename=document.title,
        file_type=document.source_type,
        status=document.status,
        total_pages=len(document.pages or []),
        total_chunks=len(document.chunks or []),
        tenant_id=document.tenant_id,
        created_at=document.created_at,
    )


def _chunk_response(chunk: DocumentChunk) -> DocumentChunkRead:
    metadata: dict[str, Any] = chunk.metadata_ or {}
    return DocumentChunkRead(
        id=chunk.id,
        index=chunk.chunk_index,
        page=metadata.get("page") or metadata.get("page_number"),
        heading=metadata.get("heading"),
    )


def _chunk_list_item(chunk: DocumentChunk) -> DocumentChunkListItem:
    metadata: dict[str, Any] = chunk.metadata_ or {}
    return DocumentChunkListItem(
        id=chunk.id,
        index=chunk.chunk_index,
        page=metadata.get("page") or metadata.get("page_number"),
        heading=metadata.get("heading"),
        text=chunk.content,
        section=metadata.get("section"),
        tags=metadata.get("tags") if isinstance(metadata.get("tags"), list) else [],
        embedding_hash=metadata.get("embedding_hash"),
        vector_id=metadata.get("vector_id"),
    )


@router.post("", response_model=DocumentCreateResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentCreateResponse:
    _ensure_tenant(current_user, payload.tenant_id)
    _validate_source(db, current_user.tenant_id, payload.source_id)

    metadata = dict(payload.metadata)
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    document = Document(
        tenant_id=current_user.tenant_id,
        source_id=payload.source_id,
        title=payload.filename,
        source_type=payload.file_type,
        mime_type=payload.file_type,
        path=payload.file_path,
        file_size=payload.file_size,
        status="pending",
        tags=tags,
        metadata_=metadata,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return _document_response(document)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    tenant_id: Optional[UUID] = None,
    source_id: Optional[UUID] = None,
    status: Optional[str] = None,
    page: int = 1,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    if tenant_id is not None:
        _ensure_tenant(current_user, tenant_id)

    page = max(page, 1)
    chunk_counts = (
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.id).label("total_chunks"))
        .filter(DocumentChunk.tenant_id == current_user.tenant_id)
        .group_by(DocumentChunk.document_id)
        .subquery()
    )
    query = (
        db.query(Document, func.coalesce(chunk_counts.c.total_chunks, 0))
        .outerjoin(chunk_counts, Document.id == chunk_counts.c.document_id)
        .filter(Document.tenant_id == current_user.tenant_id)
    )
    if source_id is not None:
        query = query.filter(Document.source_id == source_id)
    if status is not None:
        query = query.filter(Document.status == status)

    rows = query.order_by(Document.created_at.desc()).offset((page - 1) * 20).limit(20).all()
    return DocumentListResponse(
        items=[
            DocumentListItem(
                id=document.id,
                filename=document.title,
                status=document.status,
                total_chunks=total_chunks,
            )
            for document, total_chunks in rows
        ]
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    document = _get_document_or_404(db, current_user, document_id)
    base = _document_response(document).model_dump()
    return DocumentRead(
        **base,
        summary=document.summary,
        keywords=document.keywords or [],
        metadata=document.metadata_ or {},
        chunks=[_chunk_response(chunk) for chunk in sorted(document.chunks, key=lambda item: item.chunk_index)],
        indexed_at=document.indexed_at,
    )


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    document = _get_document_or_404(db, current_user, document_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "metadata" in update_data:
        document.metadata_ = update_data["metadata"] or {}
        tags = document.metadata_.get("tags")
        if isinstance(tags, list):
            document.tags = tags
    if "status" in update_data:
        document.status = update_data["status"]

    db.commit()
    db.refresh(document)
    return get_document(document_id, current_user, db)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    document = _get_document_or_404(db, current_user, document_id)
    delete_document_vectors(current_user.tenant_id, document.id)
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/chunks",
    response_model=DocumentChunksCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Chunks"],
)
def create_document_chunks(
    document_id: UUID,
    payload: DocumentChunksCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentChunksCreateResponse:
    document = _get_document_or_404(db, current_user, document_id)
    existing_indexes = {
        chunk_index
        for (chunk_index,) in db.query(DocumentChunk.chunk_index)
        .filter(DocumentChunk.document_id == document.id, DocumentChunk.tenant_id == current_user.tenant_id)
        .all()
    }
    requested_indexes = [chunk.index for chunk in payload.chunks]
    if len(requested_indexes) != len(set(requested_indexes)):
        raise HTTPException(status_code=409, detail="Duplicate chunk index in request")
    duplicates = sorted(set(requested_indexes).intersection(existing_indexes))
    if duplicates:
        raise HTTPException(status_code=409, detail=f"Chunk index already exists: {duplicates[0]}")

    created_chunks: list[DocumentChunk] = []
    seen_pages = set()
    for chunk_in in payload.chunks:
        metadata = {
            "page": chunk_in.page,
            "section": chunk_in.section,
            "heading": chunk_in.heading,
            "tags": chunk_in.tags,
            "embedding_hash": chunk_in.embedding_hash,
            "vector_id": chunk_in.vector_id,
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}
        chunk = DocumentChunk(
            tenant_id=current_user.tenant_id,
            document_id=document.id,
            chunk_index=chunk_in.index,
            content=chunk_in.text,
            metadata_=metadata,
        )
        db.add(chunk)
        created_chunks.append(chunk)

        if chunk_in.page is not None and chunk_in.page not in seen_pages:
            seen_pages.add(chunk_in.page)
            existing_page = (
                db.query(DocumentPage)
                .filter(
                    DocumentPage.document_id == document.id,
                    DocumentPage.tenant_id == current_user.tenant_id,
                    DocumentPage.page_number == chunk_in.page,
                )
                .first()
            )
            if existing_page is None:
                db.add(
                    DocumentPage(
                        tenant_id=current_user.tenant_id,
                        document_id=document.id,
                        page_number=chunk_in.page,
                        metadata_={"source": "chunk_ingestion"},
                    )
                )

    document.status = "indexed"
    document.indexed_at = datetime.utcnow()
    db.commit()
    for chunk in created_chunks:
        db.refresh(chunk)

    return DocumentChunksCreateResponse(
        document_id=document.id,
        chunks_created=len(created_chunks),
        chunks=[
            DocumentChunkCreateItem(
                id=chunk.id,
                index=chunk.chunk_index,
                page=(chunk.metadata_ or {}).get("page"),
            )
            for chunk in sorted(created_chunks, key=lambda item: item.chunk_index)
        ],
    )


@router.get("/{document_id}/chunks", response_model=DocumentChunksListResponse, tags=["Chunks"])
def list_document_chunks(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentChunksListResponse:
    document = _get_document_or_404(db, current_user, document_id)
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id, DocumentChunk.tenant_id == current_user.tenant_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    return DocumentChunksListResponse(items=[_chunk_list_item(chunk) for chunk in chunks])
