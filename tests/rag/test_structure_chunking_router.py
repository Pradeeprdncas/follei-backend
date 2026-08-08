from app.services.knowledge.chunking_router import route_chunks


def test_router_dispatches_layout_and_keeps_heading_path():
    result = route_chunks(
        "handbook.docx",
        [{"page": 2, "heading": "Refund Policy", "text": "Refunds are available for 45 days."}],
        metadata={"source_id": "source-1", "tenant_id": "tenant-1"},
    )

    assert result.strategy == "layout_aware"
    assert result.chunks[0]["heading_path"] == ["Refund Policy"]
    assert result.chunks[0]["source_id"] == "source-1"


def test_router_dispatches_table_preserving_and_repeats_header():
    result = route_chunks(
        "pricing.xlsx",
        [{"page": 1, "heading": "Pricing", "text": "Plan | Price\nStarter | $10\nBusiness | $50"}],
        metadata={"source_id": "source-1", "tenant_id": "tenant-1"},
    )

    assert result.strategy == "table_preserving"
    assert len(result.chunks) == 2
    assert all(chunk["chunk_type"] == "table" for chunk in result.chunks)
    assert all(chunk["text"].startswith("Plan | Price\n") for chunk in result.chunks)


def test_router_dispatches_plain_prose_semantically():
    result = route_chunks(
        "website.txt",
        [{"page": 1, "text": "A plain paragraph without a heading. " * 80}],
        metadata={"source_id": "source-1", "tenant_id": "tenant-1"},
    )

    assert result.strategy == "semantic"
    assert len(result.chunks) > 1
    assert all(chunk["chunk_type"] == "prose" for chunk in result.chunks)


def test_router_creates_exactly_one_chunk_per_faq():
    result = route_chunks(
        "faqs.txt",
        [{"page": 1, "text": "Q: What is the refund window?\nA: 45 days.\nQ: Do you support SSO?\nA: Yes, on Business."}],
        metadata={"category": "faqs", "source_id": "source-1", "tenant_id": "tenant-1"},
    )

    assert result.strategy == "faq_pair"
    assert len(result.chunks) == 2
    assert all(chunk["chunk_type"] == "faq" for chunk in result.chunks)
    assert result.chunks[0]["heading_path"][0] == "FAQs"


def test_router_creates_exactly_one_chunk_per_slide_with_notes():
    result = route_chunks(
        "pitch.pptx",
        [
            {"page": 1, "heading": "Problem", "text": "Problem\nManual work\nSpeaker notes:\nExplain the cost."},
            {"page": 2, "heading": "Solution", "text": "Solution\nAutonomous workflows"},
        ],
        metadata={"source_id": "source-1", "tenant_id": "tenant-1"},
    )

    assert result.strategy == "slide"
    assert len(result.chunks) == 2
    assert all(chunk["chunk_type"] == "slide" for chunk in result.chunks)
    assert "Speaker notes" in result.chunks[0]["text"]


def test_every_chunk_has_the_shared_metadata_envelope():
    result = route_chunks(
        "plain.txt",
        [{"page": 7, "text": "A retrievable statement."}],
        metadata={"category": "products", "source_id": "source-9", "tenant_id": "tenant-4"},
    )

    chunk = result.chunks[0]
    assert set(chunk) >= {
        "chunk_id", "source_id", "tenant_id", "category", "heading_path",
        "page_number", "chunk_type", "token_count", "text",
    }
