"""Document repository — CRUD + queries."""
from sqlalchemy.orm import Session
from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, doc: Document) -> Document:
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_by_id(self, doc_id: str) -> Document | None:
        return self.db.query(Document).filter(Document.id == doc_id).first()

    def get_by_tenant(self, tenant_id: str) -> list[Document]:
        return self.db.query(Document).filter(Document.tenant_id == tenant_id).all()

    def update_status(self, doc_id: str, status: str) -> None:
        self.db.query(Document).filter(Document.id == doc_id).update({"status": status})
        self.db.commit()

    def update_summary(self, doc_id: str, summary: str, keywords: str, total_chunks: int) -> None:
        self.db.query(Document).filter(Document.id == doc_id).update({
            "summary": summary,
            "keywords": keywords,
            "total_chunks": total_chunks,
            "status": "indexed",
        })
        self.db.commit()
