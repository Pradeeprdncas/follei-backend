from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.knowledge.document import ChunkEmbedding, DocumentChunk
from app.models.tenancy import User
from app.auth.dependencies import get_current_user
from app.schemas.document import ChunkEmbeddingCreate, ChunkEmbeddingResponse

router = APIRouter(prefix="/chunks", tags=["Chunks"])


def _get_chunk_or_404(db: Session, current_user: User, chunk_id: UUID) -> DocumentChunk:
    chunk = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.id == chunk_id, DocumentChunk.tenant_id == current_user.tenant_id)
        .first()
    )
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return chunk


@router.post("/{chunk_id}/embeddings", response_model=ChunkEmbeddingResponse, status_code=status.HTTP_201_CREATED)
def create_chunk_embedding(
    chunk_id: UUID,
    payload: ChunkEmbeddingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkEmbeddingResponse:
    chunk = _get_chunk_or_404(db, current_user, chunk_id)
    embedding = (
        db.query(ChunkEmbedding)
        .filter(
            ChunkEmbedding.chunk_id == chunk.id,
            ChunkEmbedding.tenant_id == current_user.tenant_id,
            ChunkEmbedding.embedding_model == payload.model,
        )
        .first()
    )

    if embedding is None:
        embedding = ChunkEmbedding(
            tenant_id=current_user.tenant_id,
            chunk_id=chunk.id,
            embedding_model=payload.model,
            vector_id=payload.vector_id,
            dimensions=payload.dimensions,
            distance_metric=payload.distance_metric,
        )
        db.add(embedding)
    else:
        embedding.vector_id = payload.vector_id
        embedding.dimensions = payload.dimensions
        embedding.distance_metric = payload.distance_metric

    metadata = dict(chunk.metadata_ or {})
    metadata["vector_id"] = payload.vector_id
    metadata["embedding_model"] = payload.model
    if payload.dimensions is not None:
        metadata["embedding_dimensions"] = payload.dimensions
    if payload.distance_metric is not None:
        metadata["distance_metric"] = payload.distance_metric
    chunk.metadata_ = metadata

    db.commit()
    db.refresh(embedding)
    return ChunkEmbeddingResponse(
        id=embedding.id,
        chunk_id=embedding.chunk_id,
        vector_id=embedding.vector_id,
        model=embedding.embedding_model,
        dimensions=embedding.dimensions,
        distance_metric=embedding.distance_metric,
        created_at=embedding.created_at,
    )
