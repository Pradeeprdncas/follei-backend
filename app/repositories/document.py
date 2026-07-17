"""Document repository for the canonical UUID document model."""
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
        doc = self.get_by_id(doc_id)
        if doc:
            doc.status = status
            self.db.commit()

    def update_summary(self, doc_id: str, summary: str, keywords: str | list[str], total_chunks: int) -> None:
        """Persist canonical fields and compatibility metadata in one transaction."""
        doc = self.get_by_id(doc_id)
        if not doc:
            return
        doc.summary = summary
        doc.keywords = keywords if isinstance(keywords, list) else [item.strip() for item in keywords.split(",") if item.strip()]
        doc.total_chunks = total_chunks
        doc.status = "indexed"
        self.db.commit()
