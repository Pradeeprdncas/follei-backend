from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    source_id: Optional[UUID] = None
    filename: str = Field(..., min_length=1)
    file_path: Optional[str] = None
    file_type: str = Field(..., min_length=1)
    file_size: Optional[int] = Field(default=None, ge=0)
    tenant_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    metadata: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class DocumentChunkRead(BaseModel):
    id: UUID
    index: int
    page: Optional[int] = None
    heading: Optional[str] = None


class DocumentChunkCreate(BaseModel):
    index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    page: Optional[int] = Field(default=None, ge=1)
    section: Optional[str] = None
    heading: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    embedding_hash: Optional[str] = None
    vector_id: Optional[str] = None


class DocumentChunksCreate(BaseModel):
    chunks: list[DocumentChunkCreate] = Field(..., min_length=1)


class DocumentChunkCreateItem(BaseModel):
    id: UUID
    index: int
    page: Optional[int] = None


class DocumentChunksCreateResponse(BaseModel):
    document_id: UUID
    chunks_created: int
    chunks: list[DocumentChunkCreateItem]


class DocumentChunkListItem(DocumentChunkRead):
    text: str
    section: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    embedding_hash: Optional[str] = None
    vector_id: Optional[str] = None


class DocumentChunksListResponse(BaseModel):
    items: list[DocumentChunkListItem]


class ChunkEmbeddingCreate(BaseModel):
    vector_id: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    dimensions: Optional[int] = Field(default=None, gt=0)
    distance_metric: Optional[str] = None


class ChunkEmbeddingResponse(BaseModel):
    id: UUID
    chunk_id: UUID
    vector_id: str
    model: str
    dimensions: Optional[int] = None
    distance_metric: Optional[str] = None
    created_at: datetime


class DocumentCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: Optional[UUID] = None
    filename: str
    file_type: str
    status: str
    total_pages: int
    total_chunks: int
    tenant_id: UUID
    created_at: datetime


class DocumentListItem(BaseModel):
    id: UUID
    filename: str
    status: str
    total_chunks: int


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]


class DocumentRead(DocumentCreateResponse):
    summary: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[DocumentChunkRead] = Field(default_factory=list)
    indexed_at: Optional[datetime] = None
