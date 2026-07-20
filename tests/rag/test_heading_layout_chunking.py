"""Regression coverage for heading-aware routing of ordinary text documents."""
from app.services.rag.chunking.registry import chunk_document


def test_prose_catalog_keeps_headings_instead_of_becoming_table_rows():
    pages = [{"page": 1, "text": """FOLLEI VALIDATION CATALOG
Enterprise Support Plan
Priority support is available for enterprise customers.
Refund Policy
The refund window is 45 days from purchase.
Enterprise Pricing
Enterprise tier price: USD 999 per month."""}]

    chunks = chunk_document("validation.txt", pages, metadata={"category": "catalog"})

    assert chunks
    assert all(chunk["chunk_type"] != "table_row" for chunk in chunks)
    assert {chunk["heading"] for chunk in chunks} >= {"Refund Policy", "Enterprise Pricing"}
    refund = next(chunk for chunk in chunks if "45 days" in chunk["text"])
    assert refund["section_path"] == ["Refund Policy"]


def test_mixed_markdown_document_keeps_headings_when_it_contains_some_tables():
    pages = [{"page": 1, "text": """# Refund Policy
The refund window is 45 days.
| Requirement | Value |
|---|---|
| Window | 45 days |
# Pricing
Enterprise costs USD 999 per month."""}]
    chunks = chunk_document("terms.txt", pages, metadata={"category": "policy"})
    assert all(chunk["chunk_type"] != "table_row" for chunk in chunks)
    assert next(chunk for chunk in chunks if "45 days" in chunk["text"])["section_path"] == ["Refund Policy"]
