from pathlib import Path
import asyncio
import pytest
from app.services.rag import classification
from app.services.rag.document_identity import next_version, sha256_file, stable_upload_uri
from app.services.rag.chunking.registry import strategy_for
from app.services.rag.chunking.table_aware import TableAwareChunker
from app.services.rag.chunking.turn_aware import TurnAwareChunker


def test_document_hash_and_stable_upload_uri(tmp_path: Path):
    source = tmp_path / "pricing.pdf"
    source.write_bytes(b"same business document")
    assert sha256_file(source) == sha256_file(source)
    assert stable_upload_uri("tenant-a", "../pricing.pdf") == "upload://tenant-a/pricing.pdf"


def test_version_chain_is_monotonic():
    assert next_version(None) == 1
    assert next_version(1) == 2
    assert next_version(12) == 13


@pytest.mark.parametrize(
    ("filename", "text", "expected"),
    [
        ("pricing.pdf", "Enterprise plan price list", "pricing"),
        ("refund-policy.pdf", "Our privacy policy and refund terms", "policy"),
        ("faq.pdf", "Frequently asked questions and answers", "faq"),
        ("sales-sop.docx", "Standard operating procedure for discovery", "sop"),
        ("products.xlsx", "Product catalog SKU specification", "catalog"),
    ],
)
def test_classifier_spot_checks_and_category_routing(monkeypatch, filename, text, expected):
    monkeypatch.setattr(classification._settings, "RAG_ENABLE_DOCUMENT_CLASSIFICATION", False)
    category = asyncio.run(classification.classify_document(
        filename=filename, source_type=Path(filename).suffix.lstrip("."), pages=[{"text": text, "page": 1}],
    ))
    assert category == expected
    assert isinstance(strategy_for("pricing", "pricing.pdf"), TableAwareChunker)
    assert isinstance(strategy_for("transcript", "call.txt"), TurnAwareChunker)
