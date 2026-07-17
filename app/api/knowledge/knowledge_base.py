from fastapi import APIRouter, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import Optional
from loguru import logger

from app.database.session import get_db
from app.models.knowledge.knowledge_base import KnowledgeBase
from app.schemas.knowledge import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


@router.post("/upload", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def upload_knowledge():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This upload endpoint is deprecated. Use POST /upload instead.",
    )


@router.get("", response_model=KnowledgeBaseListResponse)
def list_knowledge_base(
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
) -> KnowledgeBaseListResponse:
    db = next(get_db())
    try:
        from sqlalchemy import select, func

        query = select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)

        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar()

        query = query.order_by(KnowledgeBase.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = db.execute(query)
        items = result.scalars().all()

        return KnowledgeBaseListResponse(
            items=[
                KnowledgeBaseResponse(
                    id=str(kb.id),
                    title=kb.title,
                    description=kb.description,
                    file_type=kb.file_type,
                    file_path=kb.file_path,
                    url=kb.url,
                    status=kb.status,
                    chunk_count=kb.chunk_count,
                    tenant_id=str(kb.tenant_id),
                    created_at=kb.created_at,
                    updated_at=kb.updated_at,
                )
                for kb in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    finally:
        db.close()


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_item(kb_id: str) -> KnowledgeBaseResponse:
    db = next(get_db())
    try:
        kb = db.get(KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base item not found")

        return KnowledgeBaseResponse(
            id=str(kb.id),
            title=kb.title,
            description=kb.description,
            file_type=kb.file_type,
            file_path=kb.file_path,
            url=kb.url,
            status=kb.status,
            chunk_count=kb.chunk_count,
            tenant_id=str(kb.tenant_id),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
    finally:
        db.close()


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_item(kb_id: str):
    db = next(get_db())
    try:
        kb = db.get(KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base item not found")

        if kb.file_path:
            import os
            if os.path.exists(kb.file_path):
                os.remove(kb.file_path)

        db.delete(kb)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally:
        db.close()
