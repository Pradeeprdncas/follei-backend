from sqlalchemy.orm import configure_mappers


def test_canonical_document_and_chunk_models_do_not_duplicate_tables():
    import app.models as models

    configure_mappers()
    assert models.Document.__tablename__ == "documents"
    assert models.Chunk.__tablename__ == "document_chunks"
    assert {"category", "version", "previous_document_id", "sensitivity", "uploaded_by"}.issubset(models.Document.__table__.columns.keys())


def test_canonical_document_preserves_rag_compatibility_properties():
    from app.models import Document

    doc = Document(filename="pricing.pdf", file_path="uploads/pricing.pdf", file_type="pdf")
    doc.total_pages = 3
    doc.total_chunks = 12
    assert doc.title == "pricing.pdf"
    assert doc.path == "uploads/pricing.pdf"
    assert doc.source_type == "pdf"
    assert doc.total_pages == 3
    assert doc.total_chunks == 12
