import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    entity_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    confidence = Column(Numeric, nullable=True)
    workspace_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    document_version_id = Column(Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(40), nullable=True, index=True)
    schema_key = Column(String(120), nullable=True)
    schema_version = Column(String(32), nullable=True)
    data = Column(JSON, default=dict, nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Entity")

    tenant = relationship("Tenant")
    aliases = relationship("EntityAlias", back_populates="entity", cascade="all, delete-orphan")
    attributes = relationship("EntityAttribute", back_populates="entity", cascade="all, delete-orphan")
    outgoing_relations = relationship(
        "EntityRelation",
        back_populates="source_entity",
        cascade="all, delete-orphan",
        foreign_keys="EntityRelation.source_entity_id",
    )
    incoming_relations = relationship(
        "EntityRelation",
        back_populates="target_entity",
        cascade="all, delete-orphan",
        foreign_keys="EntityRelation.target_entity_id",
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    entity = relationship("Entity", back_populates="aliases")


class EntityAttribute(Base):
    __tablename__ = "entity_attributes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    entity = relationship("Entity", back_populates="attributes")


class EntityRelation(Base):
    __tablename__ = "entity_relations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_entity_id = Column(Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String, nullable=False)
    confidence = Column(Numeric, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    source_entity = relationship("Entity", back_populates="outgoing_relations", foreign_keys=[source_entity_id])
    target_entity = relationship("Entity", back_populates="incoming_relations", foreign_keys=[target_entity_id])
