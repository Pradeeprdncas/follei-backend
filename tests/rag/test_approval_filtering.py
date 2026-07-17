"""Fix 4 regression: draft/unapproved Postgres chunks must never reach BM25
retrieval or neighbor expansion, matching Qdrant's approval_status filtering.
"""
from types import SimpleNamespace

from app.services.rag.retrieval.approval import chunk_tags_approved, approval_tag_for
from app.services.rag.retrieval import bm25 as bm25_module
from app.services.rag.retrieval import expansion as expansion_module


def _chunk(id_, text, tags):
    return SimpleNamespace(id=id_, content=text, text=text, tags=tags, parent_chunk_id=None, prev_chunk_id=None, next_chunk_id=None, page=0, heading=None, chunk_index=0)


def test_chunk_tags_approved_helper():
    assert chunk_tags_approved(["approval:approved"]) is True
    assert chunk_tags_approved(["approval:draft"]) is False
    assert chunk_tags_approved([]) is False
    assert chunk_tags_approved(None) is False
    assert approval_tag_for("approved") == "approval:approved"


def test_bm25_excludes_draft_chunks_and_keeps_approved(monkeypatch):
    draft = _chunk("draft-1", "DRAFT_SECRET_XYZ unreleased enterprise pricing figures", ["approval:draft"])
    approved = _chunk("approved-1", "The refund window is forty five days from purchase", ["approval:approved"])
    # Filler chunks give BM25's post-filter corpus enough documents for the
    # approved chunk's matched terms to carry nonzero IDF weight (rank_bm25's
    # unsmoothed IDF can be exactly zero in a too-small corpus).
    filler_a = _chunk("filler-1", "Unrelated onboarding checklist content for new customers", ["approval:approved"])
    filler_b = _chunk("filler-2", "Support ticket escalation process overview document", ["approval:approved"])

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_texts_for_bm25(self, tenant_id):
            return [draft, approved, filler_a, filler_b]

    monkeypatch.setattr(bm25_module, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(bm25_module, "ChunkRepository", FakeRepo)

    results = bm25_module.retrieve_bm25("refund window purchase", "tenant-a", top_k=10)

    chunk_ids = [r["chunk_id"] for r in results]
    assert "approved-1" in chunk_ids
    assert "draft-1" not in chunk_ids
    assert not any("DRAFT_SECRET_XYZ" in r["text"] for r in results)


def test_bm25_returns_nothing_when_only_draft_chunks_exist(monkeypatch):
    draft = _chunk("draft-1", "unapproved content", ["approval:draft"])

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_texts_for_bm25(self, tenant_id):
            return [draft]

    monkeypatch.setattr(bm25_module, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(bm25_module, "ChunkRepository", FakeRepo)

    assert bm25_module.retrieve_bm25("unapproved", "tenant-a") == []


def test_expand_neighbors_excludes_draft_seed_and_draft_neighbor(monkeypatch):
    approved_seed = _chunk("seed-1", "approved seed text", ["approval:approved"])
    approved_seed.parent_chunk_id = "neighbor-approved"
    approved_seed.prev_chunk_id = "neighbor-draft"
    approved_seed.next_chunk_id = None

    draft_seed = _chunk("seed-2", "draft seed text", ["approval:draft"])
    draft_seed.parent_chunk_id = "should-never-be-fetched"

    neighbor_approved = _chunk("neighbor-approved", "approved neighbor text", ["approval:approved"])
    neighbor_draft = _chunk("neighbor-draft", "DRAFT_SECRET neighbor text", ["approval:draft"])

    chunks_by_id = {
        "seed-1": approved_seed,
        "seed-2": draft_seed,
        "neighbor-approved": neighbor_approved,
        "neighbor-draft": neighbor_draft,
    }

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, cid):
            return chunks_by_id.get(cid)

    monkeypatch.setattr(expansion_module, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(expansion_module, "ChunkRepository", FakeRepo)

    results = expansion_module.expand_neighbors(["seed-1", "seed-2"])
    ids = {r["chunk_id"] for r in results}

    assert "seed-1" in ids  # approved seed included (self is a "neighbor")
    assert "neighbor-approved" in ids
    assert "neighbor-draft" not in ids  # draft neighbor of an approved seed still excluded
    assert "seed-2" not in ids  # draft seed excluded entirely, its neighbors never fetched
    assert not any("DRAFT_SECRET" in r["text"] for r in results)
