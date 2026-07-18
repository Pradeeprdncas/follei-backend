"""Onboarding item 5 regression: document status is derived, not reprocessed."""
from types import SimpleNamespace

from app.services.knowledge.document_status import _derive_status


def _doc(status):
    return SimpleNamespace(status=status)


def test_processing_with_no_chunks_is_parsing():
    assert _derive_status(_doc("processing"), has_chunks=False, has_pending_drafts=False) == "parsing"


def test_processing_with_chunks_is_indexing():
    assert _derive_status(_doc("processing"), has_chunks=True, has_pending_drafts=False) == "indexing"


def test_indexed_with_pending_drafts_is_extraction_pending():
    assert _derive_status(_doc("indexed"), has_chunks=True, has_pending_drafts=True) == "extraction_pending"


def test_indexed_with_no_pending_drafts_is_extraction_ready():
    assert _derive_status(_doc("indexed"), has_chunks=True, has_pending_drafts=False) == "extraction_ready"


def test_failed_status_is_always_failed_regardless_of_other_signals():
    assert _derive_status(_doc("failed"), has_chunks=True, has_pending_drafts=True) == "failed"


def test_unknown_or_pending_status_defaults_to_queued():
    assert _derive_status(_doc("pending"), has_chunks=False, has_pending_drafts=False) == "queued"
