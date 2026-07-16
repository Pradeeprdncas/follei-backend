import time
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.models.domain import FAQ, Policy, Procedure
from app.models.knowledge.document import Document, DocumentChunk, KnowledgeSource
from app.models.tenancy import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/knowledge", tags=["Knowledge & RAG"])
faq_router = APIRouter(prefix="/faqs", tags=["Knowledge & RAG"])
policy_router = APIRouter(prefix="/policies", tags=["Knowledge & RAG"])
procedure_router = APIRouter(prefix="/procedures", tags=["Knowledge & RAG"])


class SourceIn(BaseModel):
    name: str
    type: str
    tenant_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class SearchIn(BaseModel):
    query: str
    tenant_id: UUID
    source_ids: list[UUID] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] = Field(default_factory=dict)


class FAQIn(BaseModel):
    question: str
    answer: str
    tenant_id: UUID
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source_document_id: Optional[UUID] = None


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


class PolicyIn(BaseModel):
    title: str
    content: str
    tenant_id: UUID
    category: Optional[str] = None
    effective_date: Optional[date] = None
    version: Optional[str] = None


class ProcedureIn(BaseModel):
    title: str
    steps: list[dict[str, Any]]
    tenant_id: UUID
    category: Optional[str] = None


def _ensure_tenant(user: User, tenant_id: UUID) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _status(is_active: bool) -> str:
    return "active" if is_active else "inactive"


def _source_payload(db: Session, source: KnowledgeSource, include_docs: bool = False) -> dict[str, Any]:
    chunk_count = (
        db.query(func.count(DocumentChunk.id))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.source_id == source.id, Document.tenant_id == source.tenant_id)
        .scalar()
    )
    documents = source.documents or []
    data = {
        "id": source.id,
        "name": source.name,
        "type": source.source_type,
        "tenant_id": source.tenant_id,
        "config": source.config or {},
        "status": _status(source.is_active),
        "document_count": len(documents),
        "total_chunks": chunk_count or 0,
        "created_at": source.created_at,
    }
    if include_docs:
        data["documents"] = [{"id": doc.id, "filename": doc.title, "status": doc.status} for doc in documents]
    return data


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    source = KnowledgeSource(
        tenant_id=user.tenant_id,
        name=payload.name,
        source_type=payload.type,
        config=payload.config,
        is_active=payload.status == "active",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_payload(db, source)


@router.get("/sources")
def list_sources(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sources = (
        db.query(KnowledgeSource)
        .options(selectinload(KnowledgeSource.documents))
        .filter(KnowledgeSource.tenant_id == user.tenant_id)
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )
    return {"items": [_source_payload(db, source) for source in sources]}


@router.get("/sources/{source_id}")
def get_source(source_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    source = (
        db.query(KnowledgeSource)
        .options(selectinload(KnowledgeSource.documents))
        .filter(KnowledgeSource.id == source_id, KnowledgeSource.tenant_id == user.tenant_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return _source_payload(db, source, include_docs=True)


@router.patch("/sources/{source_id}")
def update_source(source_id: UUID, payload: SourceUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id, KnowledgeSource.tenant_id == user.tenant_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        source.name = data["name"]
    if "config" in data:
        source.config = data["config"] or {}
    if "status" in data:
        source.is_active = data["status"] == "active"
    db.commit()
    db.refresh(source)
    return _source_payload(db, source)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id, KnowledgeSource.tenant_id == user.tenant_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    db.delete(source)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search")
def search_knowledge(payload: SearchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    started = time.perf_counter()
    _ensure_tenant(user, payload.tenant_id)
    query = db.query(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id).filter(DocumentChunk.tenant_id == user.tenant_id)
    if payload.source_ids:
        query = query.filter(Document.source_id.in_(payload.source_ids))
    document_types = payload.filters.get("document_types") or []
    if document_types:
        query = query.filter(Document.source_type.in_(document_types))
    rows = query.order_by(DocumentChunk.created_at.desc()).limit(payload.top_k * 5).all()
    terms = [term.lower() for term in payload.query.split() if term]
    filter_tags = set(payload.filters.get("tags") or [])
    results = []
    for chunk, document in rows:
        metadata = chunk.metadata_ or {}
        tags = set(metadata.get("tags") or [])
        if filter_tags and not filter_tags.intersection(tags):
            continue
        text = chunk.content or ""
        hits = sum(1 for term in terms if term in text.lower())
        score = 0.5 + min(hits, 5) / 10
        results.append({
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_name": document.title,
            "page": metadata.get("page"),
            "heading": metadata.get("heading"),
            "text": text,
            "score": round(score, 4),
            "metadata": metadata,
        })
        if len(results) >= payload.top_k:
            break
    return {"query": payload.query, "results": results, "total_results": len(results), "latency_ms": int((time.perf_counter() - started) * 1000)}


@faq_router.post("", status_code=status.HTTP_201_CREATED)
def create_faq(payload: FAQIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    metadata = {"category": payload.category, "source_document_id": str(payload.source_document_id) if payload.source_document_id else None}
    faq = FAQ(tenant_id=user.tenant_id, question=payload.question, answer=payload.answer, tags=payload.tags)
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return {"id": faq.id, "question": faq.question, "answer": faq.answer, "category": metadata["category"], "tags": faq.tags, "created_at": faq.created_at}


@faq_router.get("")
def list_faqs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(FAQ).filter(FAQ.tenant_id == user.tenant_id, FAQ.is_active.is_(True)).order_by(FAQ.created_at.desc()).all()
    return {"items": [{"id": item.id, "question": item.question, "answer": item.answer, "category": None, "tags": item.tags} for item in items]}


@faq_router.patch("/{faq_id}")
def update_faq(faq_id: UUID, payload: FAQUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == user.tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    data = payload.model_dump(exclude_unset=True)
    for field in ("question", "answer", "tags"):
        if field in data:
            setattr(faq, field, data[field])
    db.commit()
    db.refresh(faq)
    return {"id": faq.id, "question": faq.question, "answer": faq.answer, "tags": faq.tags}


@faq_router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(faq_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == user.tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@policy_router.post("", status_code=status.HTTP_201_CREATED)
def create_policy(payload: PolicyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    policy = Policy(tenant_id=user.tenant_id, title=payload.title, body=payload.content, policy_type=payload.category, metadata_={"effective_date": str(payload.effective_date) if payload.effective_date else None, "version": payload.version})
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return {"id": policy.id, "title": policy.title, "category": policy.policy_type, "version": policy.metadata_.get("version"), "created_at": policy.created_at}


@policy_router.get("")
def list_policies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Policy).filter(Policy.tenant_id == user.tenant_id).order_by(Policy.created_at.desc()).all()
    return {"items": [{"id": item.id, "title": item.title, "category": item.policy_type, "version": (item.metadata_ or {}).get("version")} for item in items]}


@procedure_router.post("", status_code=status.HTTP_201_CREATED)
def create_procedure(payload: ProcedureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    procedure = Procedure(tenant_id=user.tenant_id, title=payload.title, steps=payload.steps, metadata_={"category": payload.category})
    db.add(procedure)
    db.commit()
    db.refresh(procedure)
    return {"id": procedure.id, "title": procedure.title, "steps": procedure.steps, "category": procedure.metadata_.get("category"), "created_at": procedure.created_at}


@procedure_router.get("")
def list_procedures(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Procedure).filter(Procedure.tenant_id == user.tenant_id).order_by(Procedure.created_at.desc()).all()
    return {"items": [{"id": item.id, "title": item.title, "steps": item.steps, "category": (item.metadata_ or {}).get("category")} for item in items]}
