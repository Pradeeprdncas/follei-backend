import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    documents = relationship("Document", back_populates="source")

class Document(Base):
    """
    Represents an uploaded document or scraped source for the RAG Knowledge Base.
    """
    __tablename__ = "documents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Uuid(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False) # e.g., 'pdf', 'url', 'notion'
    source_uri = Column(Text, nullable=True)
    mime_type = Column(String, nullable=True)
    path = Column(Text, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256 for idempotency
    # Canonical cross-source lifecycle fields. Added additively by Alembic.
    category = Column(String(40), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    previous_document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    sensitivity = Column(String(32), nullable=False, default="internal")
    uploaded_by = Column(String(120), nullable=True)
    status = Column(String, default="pending")   # pending, processing, ready, failed
    
    __table_args__ = (
        Index('ix_documents_tenant_hash', 'tenant_id', 'content_hash', unique=True),
    )
    tags = Column(ARRAY(String), default=list)
    summary = Column(Text, nullable=True)
    keywords = Column(ARRAY(String), default=list)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    indexed_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="documents")
    source = relationship("KnowledgeSource", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    conversation_citations = relationship("ConversationCitation", back_populates="document")
    previous_document = relationship("Document", remote_side=[id], foreign_keys=[previous_document_id], backref="next_versions")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Document")

    @property
    def filename(self):
        return self.title

    @filename.setter
    def filename(self, value):
        self.title = value

    @property
    def file_path(self):
        return self.path

    @file_path.setter
    def file_path(self, value):
        self.path = value

    @property
    def file_type(self):
        return self.source_type

    @file_type.setter
    def file_type(self, value):
        self.source_type = value

    @property
    def total_pages(self):
        if not self.metadata_:
            return 0
        return self.metadata_.get("total_pages") or 0

    @total_pages.setter
    def total_pages(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_ = {**self.metadata_, "total_pages": value}

    @property
    def total_chunks(self):
        if not self.metadata_:
            return 0
        return self.metadata_.get("total_chunks") or 0

    @total_chunks.setter
    def total_chunks(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_ = {**self.metadata_, "total_chunks": value}


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    weaviate_object_id = Column(Uuid(as_uuid=True), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    document = relationship("Document", back_populates="chunks")
    citations = relationship("ChunkCitation", back_populates="chunk", cascade="all, delete-orphan")
    embeddings = relationship("ChunkEmbedding", back_populates="chunk", cascade="all, delete-orphan")
    conversation_citations = relationship("ConversationCitation", back_populates="chunk")

    @property
    def text(self):
        return self.content

    @text.setter
    def text(self, value):
        self.content = value

    @property
    def page(self):
        if not self.metadata_:
            return 0
        return self.metadata_.get("page") or self.metadata_.get("page_number") or 0

    @page.setter
    def page(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["page"] = value

    @property
    def heading(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("heading")

    @heading.setter
    def heading(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["heading"] = value

    @property
    def section_path(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("section_path")

    @section_path.setter
    def section_path(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["section_path"] = value

    @property
    def chunk_type(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("chunk_type")

    @chunk_type.setter
    def chunk_type(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["chunk_type"] = value

    @property
    def parent_chunk_id(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("parent_chunk_id")

    @parent_chunk_id.setter
    def parent_chunk_id(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["parent_chunk_id"] = value

    @property
    def prev_chunk_id(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("prev_chunk_id")

    @prev_chunk_id.setter
    def prev_chunk_id(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["prev_chunk_id"] = value

    @property
    def next_chunk_id(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("next_chunk_id")

    @next_chunk_id.setter
    def next_chunk_id(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["next_chunk_id"] = value

    @property
    def word_count(self):
        if not self.metadata_:
            return 0
        return self.metadata_.get("word_count") or 0

    @word_count.setter
    def word_count(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["word_count"] = value

    @property
    def section(self):
        return self.heading

    @section.setter
    def section(self, value):
        self.heading = value

    @property
    def permissions(self):
        return (self.metadata_ or {}).get("permissions", [])

    @permissions.setter
    def permissions(self, value):
        self.metadata_ = {**(self.metadata_ or {}), "permissions": value}

    @property
    def tags(self):
        if not self.metadata_:
            return []
        return self.metadata_.get("tags") or []

    @tags.setter
    def tags(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["tags"] = value

    @property
    def embedding_hash(self):
        if not self.metadata_:
            return None
        return self.metadata_.get("embedding_hash")

    @embedding_hash.setter
    def embedding_hash(self, value):
        if self.metadata_ is None:
            self.metadata_ = {}
        self.metadata_["embedding_hash"] = value


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    document = relationship("Document", back_populates="pages")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    content_hash = Column(Text, nullable=True)
    path = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    document = relationship("Document", back_populates="versions")


class ChunkCitation(Base):
    __tablename__ = "chunk_citations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    response_id = Column(Uuid(as_uuid=True), nullable=True)
    quote = Column(Text, nullable=True)
    confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    chunk = relationship("DocumentChunk", back_populates="citations")
    message = relationship("Message", back_populates="chunk_citations")


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding_model = Column(String, nullable=False)
    vector_id = Column(String, nullable=False)
    dimensions = Column(Integer, nullable=True)
    distance_metric = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    chunk = relationship("DocumentChunk", back_populates="embeddings")


class KnowledgeFeedback(Base):
    __tablename__ = "knowledge_feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query = Column(Text, nullable=True)
    result_type = Column(String, nullable=True)
    result_id = Column(Uuid(as_uuid=True), nullable=True)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    user = relationship("User")


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tags"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")




